from __future__ import annotations

import json
import datetime as dt
import hashlib
import re

from .ai_cache import invoke_cached
from .audit import log_event
from .budget import BudgetExceeded, RunBudget
from .claims import claim_policy_report, load_claims
from .orchestration_policy import load_orchestration_policy
from .provenance import decision_input_digest
from .scorecard import mark_check
from .services import role_service, service_execution_identity
from .storage import operation_lock, read_latest_session, read_text, write_text
from .workflow import load_pipeline_session, resume_sequence, run_sequence

DEFAULT_DEBATE_ROLES = ["planner", "designer", "architect", "critic", "decision_maker"]
DEFAULT_ROUND_ROLES = ["planner", "designer", "architect", "critic"]
_FENCED_JSON = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)
DEBATE_ROOT = "workspace/debates"
LATEST_DEBATE_SESSION = f"{DEBATE_ROOT}/latest-session.json"
_SESSION_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
MIN_JUDGE_MAX_TOKENS = 512


def _identity_record(service: dict[str, object]) -> dict[str, str]:
    identity = service_execution_identity(service)
    return {"provider_type": identity[0], "base_url": identity[1], "model": identity[2]}


def _configured_judge_independence(roles: list[str]) -> dict[str, object]:
    judge = service_execution_identity(role_service("decision_maker"))
    participants = [service_execution_identity(role_service(role)) for role in roles]
    if not all(judge) or not participants or any(not all(identity) for identity in participants):
        return {"assessed": False, "independent_service": None, "reason": "judge or participant service identity is incomplete"}
    independent = judge not in participants
    return {
        "assessed": True,
        "independent_service": independent,
        "reason": "judge has a distinct configured identity" if independent else "judge shares a configured participant identity",
    }


def _actual_judge_independence(
    round_results: list[dict[str, object]], judge_result: dict[str, object]
) -> tuple[dict[str, object], list[dict[str, str]], dict[str, str]]:
    participant_records: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for round_record in round_results:
        outputs = round_record.get("outputs", [])
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            service = output.get("service", {}) if isinstance(output, dict) else {}
            identity = service_execution_identity(service) if isinstance(service, dict) else ("", "", "")
            if all(identity) and identity not in seen:
                seen.add(identity)
                participant_records.append({"provider_type": identity[0], "base_url": identity[1], "model": identity[2]})
    judge_service = judge_result.get("service", {})
    judge_record = _identity_record(judge_service if isinstance(judge_service, dict) else {})
    judge_identity = service_execution_identity(judge_record)
    if not all(judge_identity) or not participant_records:
        report = {"assessed": False, "independent_service": None, "reason": "actual judge or participant identity is incomplete"}
    else:
        participant_identities = {service_execution_identity(item) for item in participant_records}
        independent = judge_identity not in participant_identities
        report = {
            "assessed": True,
            "independent_service": independent,
            "reason": "judge used a distinct actual identity" if independent else "judge shared an actual participant identity",
        }
    return report, participant_records, judge_record


def _enforce_judge_independence(policy: dict[str, object], report: dict[str, object]) -> None:
    if not policy.get("require_independent_debate_judge_service", False):
        return
    if not report.get("assessed") or not report.get("independent_service"):
        raise RuntimeError(f"independent debate judge service is required: {report.get('reason', 'not assessed')}")


def run_debate(
    prompt: str,
    roles: list[str] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
) -> list[dict[str, object]]:
    selected_roles = roles or DEFAULT_DEBATE_ROLES
    log_event("debate.started", roles=selected_roles, prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    outputs = run_sequence(
        selected_roles,
        prompt,
        system="Run this as a structured design debate. Each role must answer with decisions, risks, and unresolved questions.",
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
    )
    mark_check("debate", True, f"{len(outputs)} role output(s)")
    log_event("debate.completed", roles=selected_roles, outputs=len(outputs))
    return outputs


def debate_summary(outputs: list[dict[str, object]]) -> str:
    return json.dumps(
        [{"role": item.get("role", ""), "content": item.get("content", "")} for item in outputs],
        indent=2,
        ensure_ascii=False,
    )


def _normalize_string_collections(verdict: dict[str, object]) -> None:
    fields = (
        "agreements",
        "disagreements",
        "risks",
        "implementation_brief",
        "verification_commands",
        "claim_ids",
    )
    for name in fields:
        value = verdict.get(name)
        if isinstance(value, str):
            text = value.strip()
            verdict[name] = [text] if text else []


def _parse_judge(content: str) -> dict[str, object]:
    candidate = content.strip()
    match = _FENCED_JSON.search(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        verdict = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("debate judge must return one JSON object") from exc
    if not isinstance(verdict, dict):
        raise ValueError("debate judge must return one JSON object")
    required = [
        "decision", "rationale", "agreements", "disagreements", "risks", "confidence",
        "implementation_brief", "verification_commands",
        "claim_ids",
    ]
    missing = [name for name in required if name not in verdict]
    if missing:
        raise ValueError(f"debate judge response missing: {', '.join(missing)}")
    _normalize_string_collections(verdict)
    for name in ("agreements", "disagreements", "risks", "implementation_brief", "verification_commands", "claim_ids"):
        if not isinstance(verdict[name], list) or not all(isinstance(item, str) and item.strip() for item in verdict[name]):
            raise ValueError(f"debate judge {name} must be a string list")
    for name in ("implementation_brief", "verification_commands"):
        if not verdict[name]:
            raise ValueError(f"debate judge {name} must not be empty")
    for name in ("decision", "rationale"):
        if not isinstance(verdict[name], str) or not verdict[name].strip():
            raise ValueError(f"debate judge {name} must be a non-empty string")
    confidence = str(verdict["confidence"]).strip().lower()
    if confidence not in {"high", "medium", "low"}:
        raise ValueError("debate judge confidence must be high, medium, or low")
    verdict["confidence"] = confidence
    return verdict


def _verdict_sha256(verdict: dict[str, object]) -> str:
    canonical = json.dumps(verdict, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _round_sha256(round_record: dict[str, object]) -> str:
    payload = {key: value for key, value in round_record.items() if key != "round_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def debate_result_sha256(report: dict[str, object]) -> str:
    payload = {key: value for key, value in report.items() if key != "result_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def judge_provenance_sha256(report: dict[str, object]) -> str:
    payload = {
        "verdict_sha256": report.get("verdict_sha256", ""),
        "evidence_input_digest": report.get("evidence_input_digest", ""),
        "participant_services": report.get("participant_services", []),
        "judge_service": report.get("judge_service", {}),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _session_path(session_id: str) -> str:
    if not _SESSION_ID.fullmatch(session_id):
        raise ValueError("debate session id contains unsafe characters")
    return f"{DEBATE_ROOT}/{session_id}/session.json"


def _debate_input_sha256(session: dict[str, object]) -> str:
    payload = {
        "prompt": session.get("prompt"),
        "roles": session.get("roles"),
        "rounds_requested": session.get("rounds_requested"),
        "options": session.get("options"),
        "evidence_input_digest": session.get("evidence_input_digest"),
        "limits": session.get("limits"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_debate_input_sha256(session: dict[str, object]) -> str:
    payload = {
        "prompt": session.get("prompt"),
        "roles": session.get("roles"),
        "rounds_requested": session.get("rounds_requested"),
        "options": session.get("options"),
        "evidence_input_digest": session.get("evidence_input_digest"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upgrade_legacy_session(session: dict[str, object]) -> dict[str, object]:
    if session.get("format_version") not in {None, 1}:
        raise ValueError("unsupported legacy debate session format version")
    if session.get("input_sha256") != _legacy_debate_input_sha256(session):
        raise ValueError("debate session input hash mismatch")
    limits = load_orchestration_policy()
    roles = session.get("roles", [])
    results = session.get("round_results", [])
    role_count = len(roles) if isinstance(roles, list) else 0
    used_calls = 0
    if isinstance(results, list):
        for result in results:
            outputs = result.get("outputs", []) if isinstance(result, dict) else []
            used_calls += len(outputs) if isinstance(outputs, list) else 0
    active_pipeline = bool(session.get("active_pipeline_run_id"))
    if active_pipeline:
        used_calls += role_count
    stage = str(session.get("stage", ""))
    status = str(session.get("status", ""))
    judge_started = stage == "judge" and status in {"running", "failed", "completed"}
    if judge_started or stage == "completed":
        used_calls += 1
    session["format_version"] = 2
    session["migrated_from_format_version"] = 1
    session["limits"] = limits
    session["budget"] = {
        "max_elapsed_seconds": limits["max_debate_elapsed_seconds"],
        "elapsed_seconds": 0.0,
        "max_ai_calls": limits["max_debate_ai_calls"],
        "ai_calls": used_calls,
    }
    session["round_budget_reserved"] = active_pipeline
    session["judge_attempt_inflight"] = stage == "judge" and status == "running"
    session["input_sha256"] = _debate_input_sha256(session)
    return session


def _save_debate_session(session: dict[str, object]) -> None:
    payload = json.dumps(session, indent=2, ensure_ascii=False)
    write_text(_session_path(str(session["session_id"])), payload)
    write_text(LATEST_DEBATE_SESSION, payload)


def load_debate_session(session_id: str) -> dict[str, object]:
    text = (
        read_latest_session(LATEST_DEBATE_SESSION, DEBATE_ROOT, "")
        if session_id == "latest"
        else read_text(_session_path(session_id), "")
    )
    if not text:
        raise ValueError(f"debate session not found: {session_id}")
    try:
        session = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid debate session JSON: {exc}") from exc
    if not isinstance(session, dict):
        raise ValueError("debate session must be a JSON object")
    stored_id = str(session.get("session_id", ""))
    _session_path(stored_id)
    if session_id != "latest" and stored_id != session_id:
        raise ValueError("debate session id does not match its checkpoint path")
    if "limits" not in session or "budget" not in session:
        session = _upgrade_legacy_session(session)
    elif session.get("input_sha256") != _debate_input_sha256(session):
        raise ValueError("debate session input hash mismatch")
    roles = session.get("roles")
    results = session.get("round_results")
    limits = session.get("limits")
    budget = session.get("budget")
    if not isinstance(roles, list) or not roles or not all(isinstance(item, str) for item in roles):
        raise ValueError("debate session roles are invalid")
    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        raise ValueError("debate session round results are invalid")
    if not isinstance(limits, dict) or not isinstance(budget, dict):
        raise ValueError("debate session limits or budget are invalid")
    format_version = session.get("format_version", 2)
    if not isinstance(format_version, int) or isinstance(format_version, bool) or format_version not in {2, 3}:
        raise ValueError("debate session format version is unsupported")
    status = str(session.get("status", ""))
    allowed_statuses = {"pending", "running", "failed", "completed", "stale", "budget_exhausted", "abandoned"}
    if status not in allowed_statuses:
        raise ValueError(f"debate session status is invalid: {status or 'missing'}")
    requested = session.get("rounds_requested")
    if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
        raise ValueError("debate session requested round count is invalid")
    if len(results) > requested:
        raise ValueError("debate session has more results than requested rounds")
    for index, result in enumerate(results, start=1):
        outputs = result.get("outputs")
        if result.get("round") != index or not isinstance(outputs, list):
            raise ValueError("debate session round sequence is inconsistent")
        if len(outputs) != len(roles) or any(
            not isinstance(output, dict) or output.get("role") != roles[position]
            for position, output in enumerate(outputs)
        ):
            raise ValueError(f"debate session round #{index} role outputs are inconsistent")
        if format_version >= 3 and result.get("round_sha256") != _round_sha256(result):
            raise ValueError(f"debate session round #{index} provenance hash mismatch")
    if status == "completed":
        if len(results) != requested or session.get("stage") != "completed":
            raise ValueError("completed debate session round state is inconsistent")
        report = session.get("result")
        if not isinstance(report, dict) or report.get("rounds") != results:
            raise ValueError("completed debate session result is inconsistent")
        verdict = report.get("verdict")
        if not isinstance(verdict, dict) or report.get("verdict_sha256") != _verdict_sha256(verdict):
            raise ValueError("completed debate session verdict hash mismatch")
        if report.get("judge_provenance_sha256") != judge_provenance_sha256(report):
            raise ValueError("completed debate session judge provenance hash mismatch")
        if report.get("format_version") == 2 and report.get("result_sha256") != debate_result_sha256(report):
            raise ValueError("completed debate session result provenance hash mismatch")
    return session


def _run_budget(session: dict[str, object]) -> RunBudget:
    limits = session["limits"]
    usage = session["budget"]
    return RunBudget(
        max_elapsed_seconds=int(limits["max_debate_elapsed_seconds"]),
        max_ai_calls=int(limits["max_debate_ai_calls"]),
        initial_elapsed_seconds=float(usage.get("elapsed_seconds", 0.0)),
        initial_ai_calls=int(usage.get("ai_calls", 0)),
    )


def _save_budget(session: dict[str, object], budget: RunBudget) -> None:
    session["budget"] = budget.snapshot()
    session["updated_at"] = _now()
    _save_debate_session(session)


def _budget_exhausted(session: dict[str, object], budget: RunBudget, exc: BudgetExceeded) -> None:
    session["status"] = "budget_exhausted"
    session["error"] = str(exc)
    _save_budget(session, budget)
    mark_check("debate_rounds", False, str(exc))
    log_event("debate.rounds.budget_exhausted", session_id=session["session_id"], stage=session["stage"], error=str(exc))


def load_latest_debate_verdict() -> dict[str, object] | None:
    text = read_text("workspace/debates/latest.json", "")
    if not text:
        return None
    try:
        report = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid latest debate JSON: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("verdict"), dict):
        raise ValueError("latest debate report must contain a verdict object")
    verdict = _parse_judge(json.dumps(report["verdict"], ensure_ascii=False))
    if report.get("verdict_sha256") != _verdict_sha256(verdict):
        raise ValueError("latest debate verdict hash mismatch")
    policy = load_orchestration_policy()
    stored_provenance = str(report.get("judge_provenance_sha256", ""))
    if stored_provenance and stored_provenance != judge_provenance_sha256(report):
        raise ValueError("latest debate judge provenance hash mismatch")
    if report.get("format_version") == 2 and report.get("result_sha256") != debate_result_sha256(report):
        raise ValueError("latest debate result provenance hash mismatch")
    if policy.get("require_independent_debate_judge_service", False):
        actual = report.get("actual_judge_independence", {})
        if not isinstance(actual, dict) or not actual.get("assessed") or not actual.get("independent_service"):
            raise ValueError("latest debate lacks independent actual judge evidence")
        if not stored_provenance:
            raise ValueError("latest debate lacks judge provenance hash")
    if report.get("evidence_input_digest") != decision_input_digest():
        raise ValueError("latest debate evidence snapshot is stale")
    _validate_claim_references(verdict)
    return verdict


def _validate_claim_references(verdict: dict[str, object]) -> None:
    claim_ids = [str(item) for item in verdict.get("claim_ids", [])]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("debate verdict claim_ids must be unique")
    accepted = {
        str(record.get("claim_id", ""))
        for record in load_claims()
        if str(record.get("status", "")).lower() == "accepted"
    }
    unknown = sorted(set(claim_ids) - accepted)
    if unknown:
        raise ValueError(f"debate verdict references unknown or non-accepted claim(s): {', '.join(unknown)}")
    report = claim_policy_report()
    if report["required"] and report["valid"]:
        missing = sorted(accepted - set(claim_ids))
        if missing:
            raise ValueError(f"debate verdict must reference accepted claim(s): {', '.join(missing)}")


def _bounded_excerpt(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    marker = "\n...[truncated]...\n"
    remaining = max(0, limit - len(marker))
    head = remaining // 2
    return text[:head] + marker + text[-(remaining - head):]


def _render_round_context(round_results: list[dict[str, object]], limit: int) -> str:
    entries: list[tuple[int, str, str]] = []
    for round_record in round_results:
        round_number = int(round_record.get("round", len(entries) + 1))
        outputs = round_record.get("outputs", [])
        if not isinstance(outputs, list):
            continue
        for item in outputs:
            if isinstance(item, dict):
                entries.append((round_number, str(item.get("role", "")), str(item.get("content", ""))))
    if not entries or limit <= 0:
        return ""
    per_entry = max(160, limit // len(entries) - 48)
    rendered = [
        f"Round {round_number}, role {role}:\n{_bounded_excerpt(content, per_entry)}"
        for round_number, role, content in entries
    ]
    return _bounded_excerpt("\n\n".join(rendered), limit)


def _accepted_claim_context(limit: int) -> str:
    accepted = [
        record
        for record in load_claims()
        if str(record.get("status", "")).strip().lower() == "accepted"
    ]
    if not accepted:
        return "(none; return an empty claim_ids list)"
    rendered = "\n".join(
        f"- {record.get('claim_id', '')}: {record.get('claim', '')}"
        for record in accepted
    )
    return _bounded_excerpt(rendered, limit)


def _round_prompt(
    prompt: str, round_results: list[dict[str, object]], max_prompt_chars: int
) -> str:
    instruction = (
        "\n\nReview the prior round below. Explicitly identify what you agree with, "
        "what you challenge, and what evidence or decision would resolve disagreement.\n\n"
    )
    available = max(0, max_prompt_chars - len(prompt) - len(instruction))
    prior_context = _render_round_context(round_results[-1:], available)
    if not prior_context:
        return prompt
    return prompt + instruction + prior_context


def _judge_prompt(
    prompt: str, round_results: list[dict[str, object]], max_prompt_chars: int
) -> str:
    claim_context = _accepted_claim_context(max(200, max_prompt_chars // 5))
    instructions = f"""Evaluate this multi-round design debate independently.
Return JSON only with keys decision, rationale, agreements, disagreements, risks,
confidence, implementation_brief, verification_commands, and claim_ids. The six
collection fields must be string lists; implementation_brief and
verification_commands must not be empty. claim_ids must contain every applicable
accepted claim ID listed below, copied exactly; never invent an ID. Preserve
unresolved disagreement instead of inventing consensus. Verification commands
are proposals and must still pass the project command policy.

Accepted claims:
{claim_context}

Original question:
"""
    original_limit = max(0, min(len(prompt), max_prompt_chars // 4))
    prefix = instructions + _bounded_excerpt(prompt, original_limit) + """

Debate rounds:
"""
    if len(prefix) >= max_prompt_chars:
        return _bounded_excerpt(prefix, max_prompt_chars)
    context = _render_round_context(round_results, max(0, max_prompt_chars - len(prefix)))
    return prefix + context


def _judge_max_tokens(configured: object) -> int | None:
    if configured is None:
        return None
    return max(MIN_JUDGE_MAX_TOKENS, int(configured))


def _continue_debate(session: dict[str, object]) -> dict[str, object]:
    session_id = str(session["session_id"])
    prompt = str(session["prompt"])
    roles = list(session["roles"])
    rounds = int(session["rounds_requested"])
    options = dict(session["options"])
    limits = dict(session["limits"])
    configured_independence = _configured_judge_independence(roles)
    session["configured_judge_independence"] = configured_independence
    _enforce_judge_independence(limits, configured_independence)
    round_results = list(session["round_results"])
    budget = _run_budget(session)
    max_prompt_chars = int(limits.get("max_prompt_chars", 20000))
    while len(round_results) < rounds:
        round_number = len(round_results) + 1
        current_prompt = _round_prompt(prompt, round_results, max_prompt_chars)
        session["stage"] = f"round_{round_number}"
        session["current_round"] = round_number
        session["status"] = "running"
        session["error"] = ""
        try:
            budget.check(f"debate round {round_number}")
            active_run = str(session.get("active_pipeline_run_id", ""))
            if active_run:
                _save_budget(session, budget)
                outputs = resume_sequence(active_run)
            else:
                if not session.get("round_budget_reserved", False):
                    if budget.ai_calls + len(roles) > budget.max_ai_calls:
                        raise BudgetExceeded(f"AI-call budget exhausted before debate round {round_number}")
                    for role in roles:
                        budget.reserve_ai_call(role)
                    session["round_budget_reserved"] = True
                _save_budget(session, budget)
                outputs = run_sequence(
                    roles,
                    current_prompt,
                    system=f"Structured debate round {round_number} of {rounds}. Do not claim consensus unless objections are resolved.",
                    temperature=float(options["temperature"]),
                    max_tokens=options.get("max_tokens"),
                    retries=int(options["retries"]),
                )
        except BudgetExceeded as exc:
            _budget_exhausted(session, budget, exc)
            raise
        except Exception as exc:
            try:
                pipeline = load_pipeline_session("latest")
                if pipeline.get("prompt") == current_prompt and pipeline.get("roles") == roles:
                    session["active_pipeline_run_id"] = pipeline.get("run_id", "")
            except ValueError:
                pass
            session["status"] = "failed"
            session["error"] = str(exc)
            _save_budget(session, budget)
            log_event("debate.rounds.failed", session_id=session_id, stage=session["stage"], error=str(exc))
            raise
        round_record = {"round": round_number, "outputs": outputs}
        round_record["round_sha256"] = _round_sha256(round_record)
        round_results.append(round_record)
        session["round_results"] = round_results
        session["active_pipeline_run_id"] = ""
        session["round_budget_reserved"] = False
        session["current_round"] = round_number + 1
        _save_budget(session, budget)
        write_text(
            f"{DEBATE_ROOT}/{session_id}/round-{round_number}.json",
            json.dumps(round_record, indent=2, ensure_ascii=False),
        )

    if session["evidence_input_digest"] != decision_input_digest():
        session["status"] = "stale"
        session["stage"] = "evidence_check"
        session["error"] = "debate evidence snapshot changed before judgment"
        session["updated_at"] = _now()
        _save_debate_session(session)
        raise RuntimeError(str(session["error"]))
    session["stage"] = "judge"
    session["status"] = "running"
    session["error"] = ""
    try:
        budget.check("debate judge")
        if not session.get("judge_attempt_inflight", False):
            budget.reserve_ai_call("decision_maker")
            session["judge_attempt_inflight"] = True
        _save_budget(session, budget)
        judge_result = invoke_cached(
            "decision_maker",
            _judge_prompt(prompt, round_results, max_prompt_chars),
            temperature=0.1,
            max_tokens=_judge_max_tokens(options.get("max_tokens")),
            retries=int(options["retries"]),
        )
        actual_independence, participant_services, judge_service = _actual_judge_independence(
            round_results, judge_result
        )
        session["actual_judge_independence"] = actual_independence
        session["participant_services"] = participant_services
        session["judge_service"] = judge_service
        _enforce_judge_independence(limits, actual_independence)
        verdict = _parse_judge(str(judge_result.get("content", "")))
        _validate_claim_references(verdict)
    except BudgetExceeded as exc:
        _budget_exhausted(session, budget, exc)
        raise
    except Exception as exc:
        session["judge_attempt_inflight"] = False
        session["status"] = "failed"
        session["error"] = str(exc)
        _save_budget(session, budget)
        log_event("debate.rounds.failed", session_id=session_id, stage="judge", error=str(exc))
        raise
    report = {
        "format_version": 2,
        "session_id": session_id,
        "prompt": prompt,
        "roles": roles,
        "rounds": round_results,
        "verdict": verdict,
        "verdict_sha256": _verdict_sha256(verdict),
        "evidence_input_digest": session["evidence_input_digest"],
        "configured_judge_independence": configured_independence,
        "actual_judge_independence": session.get("actual_judge_independence", {}),
        "participant_services": session.get("participant_services", []),
        "judge_service": session.get("judge_service", {}),
        "created_at": session["created_at"],
    }
    report["judge_provenance_sha256"] = judge_provenance_sha256(report)
    report["result_sha256"] = debate_result_sha256(report)
    write_text(f"{DEBATE_ROOT}/{session_id}/result.json", json.dumps(report, indent=2, ensure_ascii=False))
    write_text(f"{DEBATE_ROOT}/latest.json", json.dumps(report, indent=2, ensure_ascii=False))
    session["status"] = "completed"
    session["stage"] = "completed"
    session["judge_attempt_inflight"] = False
    session["result"] = report
    session["completed_at"] = _now()
    _save_budget(session, budget)
    mark_check("debate_rounds", True, f"{rounds} round(s), {len(roles)} role(s)")
    log_event("debate.rounds.completed", session_id=session_id, rounds=rounds, verdict_sha256=report["verdict_sha256"])
    return report


def run_debate_rounds(
    prompt: str,
    *,
    roles: list[str] | None = None,
    rounds: int = 2,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
    session_id: str | None = None,
) -> dict[str, object]:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("debate prompt must be a non-empty string")
    selected_roles = roles or DEFAULT_ROUND_ROLES
    limits = load_orchestration_policy()
    rounds = max(1, min(rounds, limits["max_debate_rounds"]))
    session_id = session_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session_path = _session_path(session_id)
    if read_text(session_path, ""):
        raise ValueError(f"debate session already exists: {session_id}")
    created_at = _now()
    session: dict[str, object] = {
        "format_version": 3,
        "session_id": session_id,
        "status": "pending",
        "stage": "round_1",
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "roles": selected_roles,
        "rounds_requested": rounds,
        "current_round": 1,
        "active_pipeline_run_id": "",
        "round_results": [],
        "round_budget_reserved": False,
        "judge_attempt_inflight": False,
        "options": {"temperature": temperature, "max_tokens": max_tokens, "retries": retries},
        "limits": limits,
        "budget": {
            "max_elapsed_seconds": limits["max_debate_elapsed_seconds"],
            "elapsed_seconds": 0.0,
            "max_ai_calls": limits["max_debate_ai_calls"],
            "ai_calls": 0,
        },
        "evidence_input_digest": decision_input_digest(),
        "error": "",
        "created_at": created_at,
        "updated_at": created_at,
    }
    session["input_sha256"] = _debate_input_sha256(session)
    _save_debate_session(session)
    log_event("debate.rounds.started", session_id=session_id, rounds=rounds, roles=selected_roles)
    return _continue_debate(session)


def resume_debate_rounds(session_id: str) -> dict[str, object]:
    resolved_id = str(load_debate_session(session_id)["session_id"]) if session_id == "latest" else session_id
    with operation_lock("debate", resolved_id):
        return _resume_debate_rounds_unlocked(resolved_id)


def _resume_debate_rounds_unlocked(session_id: str) -> dict[str, object]:
    session = load_debate_session(session_id)
    if session.get("status") == "completed":
        result = session.get("result")
        if not isinstance(result, dict):
            raise ValueError("completed debate session result is invalid")
        return result
    if session.get("status") in {"stale", "budget_exhausted"}:
        raise RuntimeError(f"debate session is terminal: {session.get('error', session.get('status'))}")
    if session.get("status") == "abandoned":
        raise RuntimeError("debate session is terminal: abandoned")
    log_event(
        "debate.rounds.resumed",
        session_id=session["session_id"],
        completed_rounds=len(session["round_results"]),
        stage=session.get("stage", ""),
    )
    return _continue_debate(session)


def abandon_debate_rounds(session_id: str, reason: str) -> dict[str, object]:
    resolved_id = str(load_debate_session(session_id)["session_id"]) if session_id == "latest" else session_id
    with operation_lock("debate", resolved_id):
        return _abandon_debate_rounds_unlocked(resolved_id, reason)


def _abandon_debate_rounds_unlocked(session_id: str, reason: str) -> dict[str, object]:
    session = load_debate_session(session_id)
    if session.get("status") == "completed":
        raise ValueError("completed debate session cannot be abandoned")
    if session.get("status") == "abandoned":
        return session
    reason = reason.strip()
    if not reason:
        raise ValueError("debate abandonment reason is required")
    if len(reason) > 1000:
        raise ValueError("debate abandonment reason must not exceed 1000 characters")
    session["status"] = "abandoned"
    session["abandonment_reason"] = reason
    session["abandoned_at"] = _now()
    session["updated_at"] = _now()
    _save_debate_session(session)
    mark_check("debate_rounds", False, f"{session['session_id']}: abandoned")
    log_event(
        "debate.rounds.abandoned",
        session_id=session["session_id"],
        completed_rounds=len(session["round_results"]),
        reason_sha256=hashlib.sha256(reason.encode("utf-8")).hexdigest(),
    )
    return session
