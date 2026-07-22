from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

from .audit import log_event
from .ai_cache import invoke_cached
from .budget import BudgetExceeded, RunBudget
from .client import invoke
from .engine import enforce_decision_gate
from .orchestration_policy import load_orchestration_policy
from .roles import ROLE_ORDER
from .scorecard import mark_check
from .storage import ensure_workspace, operation_lock, read_latest_session, read_text, write_text

RUN_ROOT = "workspace/executions/runs"
LATEST_SESSION = "workspace/executions/latest-session.json"
_RUN_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def normalize_roles(roles: list[str]) -> list[str]:
    normalized = [role.strip() for role in roles if role.strip()]
    if not normalized:
        raise ValueError("role sequence must contain at least one role")
    unknown = [role for role in normalized if role not in ROLE_ORDER]
    if unknown:
        raise ValueError(f"unknown role(s): {', '.join(unknown)}")
    if len(normalized) != len(set(normalized)):
        raise ValueError("role sequence contains duplicate roles")
    return normalized


def validate_role_sequence(roles: list[str]) -> None:
    positions = {role: ROLE_ORDER.index(role) for role in ROLE_ORDER}
    for previous, current in zip(roles, roles[1:]):
        if positions[current] < positions[previous]:
            raise ValueError(f"role sequence moves backward: {previous} -> {current}")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _new_run_id(prompt: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:10]
    return f"pipeline-{stamp}-{digest}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _result_sha256(result: dict[str, object]) -> str:
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(canonical)


def _input_sha256(
    roles: list[str], prompt: str, system: str, options: dict[str, object], limits: dict[str, object]
) -> str:
    payload = {"roles": roles, "prompt": prompt, "system": system, "options": options, "limits": limits}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(canonical)


def _session_path(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("pipeline run id contains unsafe characters")
    return f"{RUN_ROOT}/{run_id}/session.json"


def _save_session(session: dict[str, object]) -> None:
    payload = json.dumps(session, indent=2, ensure_ascii=False)
    write_text(_session_path(str(session["run_id"])), payload)
    write_text(LATEST_SESSION, payload)


def _load_json(path: str) -> dict[str, object]:
    text = read_text(path, "")
    if not text:
        raise ValueError(f"pipeline session not found: {path}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid pipeline session JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("pipeline session must be a JSON object")
    return payload


def load_pipeline_session(run_id: str) -> dict[str, object]:
    if run_id == "latest":
        text = read_latest_session(LATEST_SESSION, RUN_ROOT, "")
        if not text:
            raise ValueError(f"pipeline session not found: {LATEST_SESSION}")
        try:
            session = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid pipeline session JSON: {exc}") from exc
        if not isinstance(session, dict):
            raise ValueError("pipeline session must be a JSON object")
    else:
        session = _load_json(_session_path(run_id))
    stored_id = str(session.get("run_id", ""))
    _session_path(stored_id)
    if run_id != "latest" and stored_id != run_id:
        raise ValueError("pipeline session run id does not match its checkpoint path")
    roles = session.get("roles")
    results = session.get("results")
    if not isinstance(roles, list) or not all(isinstance(item, str) for item in roles):
        raise ValueError("pipeline session roles are invalid")
    normalized = normalize_roles(roles)
    validate_role_sequence(normalized)
    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        raise ValueError("pipeline session results are invalid")
    prompt = session.get("prompt")
    system = session.get("system")
    options = session.get("options")
    limits = session.get("limits")
    if not isinstance(prompt, str) or not isinstance(system, str) or not isinstance(options, dict) or not isinstance(limits, dict):
        raise ValueError("pipeline session input is invalid")
    expected_input = _input_sha256(normalized, prompt, system, options, limits)
    if session.get("input_sha256") != expected_input:
        raise ValueError("pipeline session input hash mismatch")
    if len(results) > len(normalized):
        raise ValueError("pipeline session has more results than roles")
    status = str(session.get("status", ""))
    allowed_statuses = {"pending", "running", "failed", "completed", "budget_exhausted", "abandoned"}
    if status not in allowed_statuses:
        raise ValueError(f"pipeline session status is invalid: {status or 'missing'}")
    if status == "completed" and len(results) != len(normalized):
        raise ValueError("completed pipeline session must contain one result per role")
    format_version = session.get("format_version", 1)
    if not isinstance(format_version, int) or isinstance(format_version, bool) or format_version not in {1, 2}:
        raise ValueError("pipeline session format version is unsupported")
    for index, result in enumerate(results, start=1):
        if result.get("index") != index or result.get("role") != normalized[index - 1]:
            raise ValueError("pipeline session result sequence is inconsistent")
        content = result.get("content")
        if not isinstance(content, str) or result.get("content_sha256") != _sha256_text(content):
            raise ValueError(f"pipeline session result #{index} content hash mismatch")
        if format_version >= 2:
            if result.get("run_id") != stored_id or result.get("prompt") != prompt:
                raise ValueError(f"pipeline session result #{index} input identity mismatch")
            if result.get("result_sha256") != _result_sha256(result):
                raise ValueError(f"pipeline session result #{index} provenance hash mismatch")
    return session


def _context_from_results(
    system: str, results: list[dict[str, object]], max_chars: int
) -> tuple[str, bool, int]:
    prefix = system.strip()
    remaining = max(0, max_chars - len(prefix) - (2 if prefix else 0))
    selected: list[str] = []
    omitted = 0
    for result in reversed(results):
        part = f"Previous role ({result['role']}) output:\n{result.get('content', '')}"
        separator = 2 if selected else 0
        if len(part) + separator <= remaining:
            selected.insert(0, part)
            remaining -= len(part) + separator
            continue
        if not selected and remaining >= 80:
            selected.insert(0, part[:remaining])
        omitted += 1
    parts = ([prefix] if prefix else []) + selected
    context = "\n\n".join(parts)
    return context, omitted > 0, omitted


def _validated_output(role: str, value: object, limits: dict[str, object]) -> str:
    content = str(value or "").strip()
    minimum = int(limits.get("min_output_chars", 20))
    maximum = int(limits.get("max_output_chars", 100000))
    if len(content) < minimum:
        raise ValueError(f"role output is shorter than {minimum} characters: {role}")
    if len(content) > maximum:
        raise ValueError(f"role output exceeds {maximum} characters: {role}")
    return content


def _execute_session(session: dict[str, object]) -> list[dict[str, object]]:
    run_id = str(session["run_id"])
    roles = list(session["roles"])
    prompt = str(session["prompt"])
    system = str(session.get("system", ""))
    options = session.get("options", {})
    limits = session.get("limits", {})
    usage = session.get("budget", {})
    if not isinstance(options, dict) or not isinstance(limits, dict) or not isinstance(usage, dict):
        raise ValueError("pipeline session options or budget are invalid")
    results = list(session.get("results", []))
    budget = RunBudget(
        max_elapsed_seconds=int(limits["max_elapsed_seconds"]),
        max_ai_calls=int(limits["max_ai_calls"]),
        initial_elapsed_seconds=float(usage.get("elapsed_seconds", 0.0)),
        initial_ai_calls=int(usage.get("ai_calls", 0)),
    )
    session["status"] = "running"
    session["error"] = ""
    session["updated_at"] = _now()
    _save_session(session)
    try:
        for index in range(len(results) + 1, len(roles) + 1):
            role = roles[index - 1]
            enforce_decision_gate(role)
            if session.get("role_call_inflight") != index:
                budget.reserve_ai_call(role)
                session["role_call_inflight"] = index
            else:
                budget.check(f"{role} in-flight AI call")
            session["budget"] = budget.snapshot()
            session["updated_at"] = _now()
            _save_session(session)
            context, context_truncated, omitted_roles = _context_from_results(
                system, results, int(limits["max_context_chars"])
            )
            log_event("pipeline.role.started", run_id=run_id, index=index, role=role)
            result = invoke_cached(
                role,
                prompt,
                system=context,
                temperature=float(options.get("temperature", 0.2)),
                max_tokens=options.get("max_tokens"),
                retries=int(options.get("retries", 1)),
                content_validator=lambda value: _validated_output(role, value, limits),
                invoke_fn=invoke,
            )
            content = str(result.get("content", ""))
            payload = {
                "run_id": run_id,
                "index": index,
                "role": role,
                "prompt": prompt,
                "system": context,
                "provider_type": result.get("provider_type", ""),
                "service": result.get("service", {}),
                "attempt": result.get("attempt", 1),
                "content": content,
                "fallback_error": result.get("fallback_error", ""),
                "primary_error": result.get("primary_error", ""),
                "diagnostics": result.get("diagnostics", {}),
                "cache_hit": bool(result.get("cache_hit", False)),
                "cache_key": result.get("cache_key", ""),
                "context_truncated": context_truncated,
                "context_omitted_roles": omitted_roles,
                "created_at": _now(),
            }
            payload["content_sha256"] = _sha256_text(str(payload["content"]))
            payload["result_sha256"] = _result_sha256(payload)
            safe_role = role.replace("/", "-")
            role_json = json.dumps(payload, indent=2, ensure_ascii=False)
            write_text(f"{RUN_ROOT}/{run_id}/{index:02d}-{safe_role}.json", role_json)
            write_text(f"workspace/executions/{index:02d}-{safe_role}.json", role_json)
            role_markdown = f"# {role}\n\n{result.get('content', '')}\n"
            write_text(f"{RUN_ROOT}/{run_id}/{index:02d}-{safe_role}.md", role_markdown)
            write_text(f"workspace/executions/{index:02d}-{safe_role}.md", role_markdown)
            results.append(payload)
            session["results"] = results
            session["next_index"] = index + 1
            session["role_call_inflight"] = 0
            session["budget"] = budget.snapshot()
            session["updated_at"] = _now()
            _save_session(session)
            log_event("pipeline.role.completed", run_id=run_id, index=index, role=role, provider_type=payload["provider_type"])
    except BudgetExceeded as exc:
        session["status"] = "budget_exhausted"
        session["error"] = str(exc)
        session["budget"] = budget.snapshot()
        session["updated_at"] = _now()
        _save_session(session)
        mark_check("pipeline", False, f"{run_id}: {exc}")
        log_event("pipeline.budget_exhausted", run_id=run_id, error=str(exc))
        raise
    except Exception as exc:
        session["role_call_inflight"] = 0
        session["status"] = "failed"
        session["error"] = str(exc)
        session["budget"] = budget.snapshot()
        session["updated_at"] = _now()
        _save_session(session)
        mark_check("pipeline", False, f"{run_id}: {exc}")
        log_event("pipeline.failed", run_id=run_id, error=str(exc), stage="execute")
        raise

    session["status"] = "completed"
    session["completed_at"] = _now()
    session["next_index"] = len(roles) + 1
    _save_session(session)
    write_text("workspace/executions/latest.json", json.dumps(session, indent=2, ensure_ascii=False))
    mark_check("pipeline", True, f"{run_id}: {len(results)} role output(s)")
    log_event("pipeline.completed", run_id=run_id, roles=roles, outputs=len(results))
    return results


def run_sequence(
    roles: list[str],
    prompt: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    ensure_workspace()
    roles = normalize_roles(roles)
    validate_role_sequence(roles)
    limits = load_orchestration_policy()
    if len(roles) > limits["max_roles"]:
        raise ValueError(f"pipeline role count exceeds policy maximum: {limits['max_roles']}")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("pipeline prompt must be a non-empty string")
    if len(prompt) > limits["max_prompt_chars"]:
        raise ValueError(f"pipeline prompt exceeds policy maximum: {limits['max_prompt_chars']} characters")
    if len(system) > limits["max_system_chars"]:
        raise ValueError(f"pipeline system prompt exceeds policy maximum: {limits['max_system_chars']} characters")
    if len(system) > limits["max_context_chars"]:
        raise ValueError(f"pipeline system prompt exceeds context maximum: {limits['max_context_chars']} characters")
    run_id = run_id or _new_run_id(prompt)
    session_path = _session_path(run_id)
    if read_text(session_path, ""):
        raise ValueError(f"pipeline run already exists: {run_id}")
    created_at = _now()
    options: dict[str, object] = {"temperature": temperature, "max_tokens": max_tokens, "retries": retries}
    session: dict[str, object] = {
        "format_version": 2,
        "run_id": run_id,
        "status": "pending",
        "roles": roles,
        "prompt": prompt,
        "system": system,
        "options": options,
        "limits": limits,
        "input_sha256": _input_sha256(roles, prompt, system, options, limits),
        "budget": {
            "max_elapsed_seconds": limits["max_elapsed_seconds"],
            "elapsed_seconds": 0.0,
            "max_ai_calls": limits["max_ai_calls"],
            "ai_calls": 0,
        },
        "results": [],
        "role_call_inflight": 0,
        "next_index": 1,
        "error": "",
        "created_at": created_at,
        "updated_at": created_at,
    }
    _save_session(session)
    log_event("pipeline.started", run_id=run_id, roles=roles, prompt_sha256=_sha256_text(prompt))
    return _execute_session(session)


def resume_sequence(run_id: str) -> list[dict[str, object]]:
    resolved_id = str(load_pipeline_session(run_id)["run_id"]) if run_id == "latest" else run_id
    with operation_lock("pipeline", resolved_id):
        return _resume_sequence_unlocked(resolved_id)


def _resume_sequence_unlocked(run_id: str) -> list[dict[str, object]]:
    session = load_pipeline_session(run_id)
    if session.get("status") == "completed":
        return list(session["results"])
    if session.get("status") == "budget_exhausted":
        raise RuntimeError(f"pipeline run is terminal: {session.get('error', 'budget exhausted')}")
    if session.get("status") == "abandoned":
        raise RuntimeError("pipeline run is terminal: abandoned")
    log_event("pipeline.resumed", run_id=session["run_id"], completed_roles=len(session["results"]))
    return _execute_session(session)


def abandon_sequence(run_id: str, reason: str) -> dict[str, object]:
    resolved_id = str(load_pipeline_session(run_id)["run_id"]) if run_id == "latest" else run_id
    with operation_lock("pipeline", resolved_id):
        return _abandon_sequence_unlocked(resolved_id, reason)


def _abandon_sequence_unlocked(run_id: str, reason: str) -> dict[str, object]:
    session = load_pipeline_session(run_id)
    if session.get("status") == "completed":
        raise ValueError("completed pipeline cannot be abandoned")
    if session.get("status") == "abandoned":
        return session
    reason = reason.strip()
    if not reason:
        raise ValueError("pipeline abandonment reason is required")
    if len(reason) > 1000:
        raise ValueError("pipeline abandonment reason must not exceed 1000 characters")
    session["status"] = "abandoned"
    session["abandonment_reason"] = reason
    session["abandoned_at"] = _now()
    session["updated_at"] = _now()
    _save_session(session)
    mark_check("pipeline", False, f"{session['run_id']}: abandoned")
    log_event(
        "pipeline.abandoned",
        run_id=session["run_id"],
        completed_roles=len(session["results"]),
        reason_sha256=_sha256_text(reason),
    )
    return session
