from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from .audit import log_event
from .ai_cache import invoke_cached
from .budget import BudgetExceeded, RunBudget
from .engine import enforce_decision_gate
from .patching import PATCH_ROOT, apply_patch_text, load_repair_policy, patch_state, rollback_patch
from .scorecard import mark_check
from .services import review_independence, service_execution_identity
from .storage import ROOT, operation_lock, read_latest_session, read_text, write_text
from .verification import run_verification_commands

REPAIR_ROOT = "workspace/repairs"
_REPAIR_ID = re.compile(r"^\d{8}T\d{12}Z$")
_FENCED_DIFF = re.compile(r"```diff\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_FENCED_JSON = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class ResumeBlocked(RuntimeError):
    pass


def _enforce_review_independence(policy: dict[str, object]) -> None:
    if not policy.get("require_independent_reviewer_service", False):
        return
    report = review_independence()
    if not report.get("assessed"):
        raise RuntimeError(f"independent reviewer service is required: {report.get('reason', 'not assessed')}")
    if not report.get("independent_service"):
        raise RuntimeError("independent reviewer service is required: coder and reviewer share provider endpoint and model")


def _record_invocation_service(
    attempt: dict[str, object], role: str, result: dict[str, object]
) -> None:
    service = result.get("service", {})
    identity = service_execution_identity(service) if isinstance(service, dict) else ("", "", "")
    attempt[f"{role}_service"] = {
        "provider_type": identity[0],
        "base_url": identity[1],
        "model": identity[2],
    }


def _enforce_actual_review_independence(
    policy: dict[str, object], attempt: dict[str, object]
) -> None:
    if not policy.get("require_independent_reviewer_service", False):
        return
    coder = attempt.get("coder_service", {})
    reviewer = attempt.get("reviewer_service", {})
    if not isinstance(coder, dict) or not isinstance(reviewer, dict):
        raise RuntimeError("strict reviewer policy requires recorded coder and reviewer service identities")
    coder_identity = service_execution_identity(coder)
    reviewer_identity = service_execution_identity(reviewer)
    if not all(coder_identity) or not all(reviewer_identity):
        raise RuntimeError("strict reviewer policy requires complete coder and reviewer service identities")
    if coder_identity == reviewer_identity:
        raise RuntimeError("strict reviewer policy blocked shared actual coder/reviewer service identity")


def review_provenance_sha256(attempt: dict[str, object]) -> str:
    payload = {
        "coder_service": attempt.get("coder_service", {}),
        "reviewer_service": attempt.get("reviewer_service", {}),
        "reviewer": attempt.get("reviewer", {}),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def repair_session_sha256(session: dict[str, object]) -> str:
    payload = {key: value for key, value in session.items() if key != "session_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _bounded_int(policy: dict[str, object], name: str, default: int, minimum: int, maximum: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"repair policy {name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"repair policy {name} must be an integer") from exc
    return max(minimum, min(parsed, maximum))


def extract_unified_diff(content: str) -> str:
    match = _FENCED_DIFF.search(content)
    if match:
        candidate = match.group(1).strip()
    else:
        start = content.find("--- ")
        candidate = content[start:].strip() if start >= 0 else ""
    if not candidate.startswith("--- "):
        raise ValueError("coder response does not contain a unified diff")
    return candidate + "\n"


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def normalize_unified_diff_hunks(diff: str) -> str:
    lines = diff.splitlines()
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        match = _HUNK_HEADER.match(lines[index])
        if not match:
            normalized.append(lines[index])
            index += 1
            continue
        end = index + 1
        old_count = 0
        new_count = 0
        while end < len(lines):
            line = lines[end]
            if _HUNK_HEADER.match(line):
                break
            if line.startswith("--- ") and end + 1 < len(lines) and lines[end + 1].startswith("+++ "):
                break
            if line.startswith("\\ No newline at end of file"):
                end += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise ValueError(f"invalid unified diff hunk line: {line[:80]}")
            if line[0] in {" ", "-"}:
                old_count += 1
            if line[0] in {" ", "+"}:
                new_count += 1
            end += 1
        normalized.append(
            f"@@ -{match.group(1)},{old_count} +{match.group(2)},{new_count} @@{match.group(3)}"
        )
        normalized.extend(lines[index + 1 : end])
        index = end
    return "\n".join(normalized).rstrip() + "\n"


def parse_json_response(content: str, label: str) -> dict[str, object]:
    candidate = content.strip()
    match = _FENCED_JSON.search(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} response must be one JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be one JSON object")
    return payload


def _failure_summary(report: dict[str, object], limit: int = 12000) -> str:
    parts = []
    for item in report.get("results", []):
        if not isinstance(item, dict) or item.get("passed"):
            continue
        parts.extend(
            [
                f"Command: {item.get('command', '')}",
                f"Return code: {item.get('returncode')}",
                f"Timed out: {item.get('timed_out', False)}",
                f"STDOUT:\n{item.get('stdout', '')}",
                f"STDERR:\n{item.get('stderr', '')}",
            ]
        )
    text = "\n\n".join(parts) or json.dumps(report, ensure_ascii=False)
    return text[-limit:]


def _allowed_context_path(rel_path: str, roots: tuple[PurePosixPath, ...]) -> Path:
    pure = PurePosixPath(rel_path.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not any(pure == root or root in pure.parents for root in roots):
        raise ValueError(f"debugger requested a file outside editable roots: {rel_path}")
    target = (ROOT / Path(*pure.parts)).resolve(strict=False)
    try:
        target.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"debugger requested a file outside the project: {rel_path}") from exc
    if not target.is_file():
        raise ValueError(f"debugger requested a missing file: {rel_path}")
    return target


def collect_file_context(files: object, policy: dict[str, object]) -> str:
    if not isinstance(files, list) or not all(isinstance(item, str) and item.strip() for item in files):
        raise ValueError("debugger files must be a list of project-relative paths")
    max_files = _bounded_int(policy, "max_context_files", 8, 1, 30)
    max_chars = _bounded_int(policy, "max_context_chars", 40000, 2000, 200000)
    roots = tuple(PurePosixPath(item.strip().replace("\\", "/")) for item in policy["editable_roots"])
    sections = []
    used = 0
    for rel_path in files[:max_files]:
        target = _allowed_context_path(rel_path, roots)
        content = target.read_text(encoding="utf-8", errors="replace")
        remaining = max_chars - used
        if remaining <= 0:
            break
        content = content[:remaining]
        sections.append(f"FILE: {rel_path}\n```text\n{content}\n```")
        used += len(content)
    return "\n\n".join(sections)


def _save_session(session_id: str, report: dict[str, object]) -> None:
    if report.get("format_version") == 2:
        report["session_sha256"] = repair_session_sha256(report)
    write_text(f"{REPAIR_ROOT}/{session_id}/session.json", json.dumps(report, indent=2, ensure_ascii=False))
    write_text(f"{REPAIR_ROOT}/latest.json", json.dumps(report, indent=2, ensure_ascii=False))


def _save_session_original(session_id: str, report: dict[str, object]) -> None:
    if report.get("format_version") == 2:
        report["session_sha256"] = repair_session_sha256(report)
    write_text(f"{REPAIR_ROOT}/{session_id}/session.json", json.dumps(report, indent=2, ensure_ascii=False))


def _debugger_prompt(task: str, failure_context: str) -> str:
    return f"""Diagnose this failed verification for the task below.
Return JSON only with keys diagnosis, files, and strategy. files must contain only project-relative files that need inspection.

Task:
{task}

Failure:
{failure_context}
"""


def _coder_prompt(task: str, decision: str, diagnosis: dict[str, object], file_context: str, failure_context: str) -> str:
    return f"""Create the smallest safe fix for the accepted task.
Return exactly one UTF-8 unified diff in a ```diff fenced block. Do not include commands or prose outside the block.
Do not modify files outside the supplied file context.

Task:
{task}

Accepted decision:
{decision}

Debugger diagnosis:
{json.dumps(diagnosis, ensure_ascii=False)}

Current files:
{file_context}

Failure:
{failure_context}
"""


def _reviewer_prompt(task: str, diff: str, verification: dict[str, object]) -> str:
    return f"""Independently review this tested patch against the accepted task.
Return JSON only with keys approved (boolean), reason, and risks (list).

Task:
{task}

Patch:
{diff}

Verification:
{json.dumps(verification, ensure_ascii=False)}
"""


def run_repair_loop(
    task: str,
    *,
    max_attempts: int | None = None,
    retries: int = 1,
    resumed_from: str = "",
    session_id: str | None = None,
) -> dict[str, object]:
    enforce_decision_gate("coder")
    policy = load_repair_policy()
    _enforce_review_independence(policy)
    configured_attempts = _bounded_int(policy, "max_attempts", 3, 1, 10)
    attempts_limit = configured_attempts if max_attempts is None else max(1, min(max_attempts, configured_attempts))
    rollback_on_failure = bool(policy.get("rollback_on_failure", True))
    reuse_ai_responses = bool(policy.get("reuse_ai_responses", True))
    cache_max_age = _bounded_int(policy, "ai_cache_max_age_seconds", 86400, 60, 604800)
    max_elapsed = _bounded_int(policy, "max_elapsed_seconds", 1800, 10, 86400)
    max_ai_calls = _bounded_int(policy, "max_ai_calls", 12, 1, 100)
    ai_max_tokens = _bounded_int(policy, "ai_max_tokens", 4096, 128, 32768)
    budget = RunBudget(max_elapsed_seconds=max_elapsed, max_ai_calls=max_ai_calls)
    session_id = session_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not _REPAIR_ID.fullmatch(session_id):
        raise ValueError("invalid repair session id")
    if read_text(f"{REPAIR_ROOT}/{session_id}/session.json", ""):
        raise ValueError(f"repair session already exists: {session_id}")
    session: dict[str, object] = {
        "format_version": 2,
        "session_id": session_id,
        "task": task,
        "started_at": _now(),
        "completed_at": "",
        "status": "running",
        "max_attempts": attempts_limit,
        "budget": budget.snapshot(),
        "attempts": [],
    }
    if resumed_from:
        session["resumed_from"] = resumed_from
    log_event("repair.started", session_id=session_id, max_attempts=attempts_limit)
    verification = run_verification_commands()
    session["initial_verification"] = verification
    try:
        budget.check("first repair attempt")
    except BudgetExceeded as exc:
        session["status"] = "budget_exhausted"
        session["budget"] = {**budget.snapshot(), "reason": str(exc)}
        session["completed_at"] = _now()
        _save_session(session_id, session)
        mark_check("repair_loop", False, str(exc))
        log_event("repair.completed", session_id=session_id, status="budget_exhausted", reason=str(exc))
        return session
    if verification.get("passed"):
        session["status"] = "already_verified"
        session["completed_at"] = _now()
        _save_session(session_id, session)
        mark_check("repair_loop", True, "verification already passed")
        return session

    failure_context = _failure_summary(verification)
    decision = read_text("docs/03-decision-record.md", "")[-12000:]
    attempts = session["attempts"]
    for attempt_number in range(1, attempts_limit + 1):
        attempt: dict[str, object] = {"attempt": attempt_number, "started_at": _now(), "status": "running"}
        attempts.append(attempt)
        _save_session(session_id, session)
        patch_metadata: dict[str, object] | None = None
        try:
            budget.check(f"attempt {attempt_number}")
            budget.reserve_ai_call("debugger")
            session["budget"] = budget.snapshot()
            debugger_result = invoke_cached(
                "debugger",
                _debugger_prompt(task, failure_context),
                max_tokens=ai_max_tokens,
                retries=retries,
                enabled=reuse_ai_responses,
                max_age_seconds=cache_max_age,
            )
            budget.check("debugger response processing")
            debugger_content = str(debugger_result.get("content", ""))
            diagnosis = parse_json_response(debugger_content, "debugger")
            file_context = collect_file_context(diagnosis.get("files", []), policy)
            attempt["debugger"] = diagnosis
            _save_session(session_id, session)

            budget.reserve_ai_call("coder")
            session["budget"] = budget.snapshot()
            coder_result = invoke_cached(
                "coder",
                _coder_prompt(task, decision, diagnosis, file_context, failure_context),
                max_tokens=ai_max_tokens,
                retries=retries,
                enabled=reuse_ai_responses,
                max_age_seconds=cache_max_age,
            )
            _record_invocation_service(attempt, "coder", coder_result)
            budget.check("coder response processing")
            coder_content = str(coder_result.get("content", ""))
            diff = extract_unified_diff(coder_content)
            write_text(f"{REPAIR_ROOT}/{session_id}/attempt-{attempt_number}.diff", diff)
            attempt["diff_file"] = f"{REPAIR_ROOT}/{session_id}/attempt-{attempt_number}.diff"
            _save_session(session_id, session)
            patch_metadata = apply_patch_text(diff)
            attempt["patch"] = patch_metadata
            _save_session(session_id, session)

            verification = run_verification_commands()
            budget.check(f"attempt {attempt_number} review")
            attempt["verification"] = verification
            _save_session(session_id, session)
            if not verification.get("passed"):
                attempt["status"] = "verification_failed"
                failure_context = _failure_summary(verification)
                if rollback_on_failure:
                    attempt["rollback"] = rollback_patch(str(patch_metadata["patch_id"]))
                attempt["completed_at"] = _now()
                _save_session(session_id, session)
                continue

            budget.reserve_ai_call("reviewer")
            session["budget"] = budget.snapshot()
            enforce_decision_gate("reviewer")
            reviewer_result = invoke_cached(
                "reviewer",
                _reviewer_prompt(task, diff, verification),
                max_tokens=ai_max_tokens,
                retries=retries,
                enabled=reuse_ai_responses,
                max_age_seconds=cache_max_age,
            )
            _record_invocation_service(attempt, "reviewer", reviewer_result)
            budget.check("reviewer response processing")
            verdict = parse_json_response(str(reviewer_result.get("content", "")), "reviewer")
            if not isinstance(verdict.get("approved"), bool):
                raise ValueError("reviewer approved must be a boolean")
            attempt["reviewer"] = verdict
            if verdict["approved"]:
                _enforce_actual_review_independence(policy, attempt)
                enforce_decision_gate("reviewer")
                attempt["status"] = "approved"
                attempt["review_provenance_sha256"] = review_provenance_sha256(attempt)
                attempt["completed_at"] = _now()
                session["status"] = "approved"
                session["completed_at"] = _now()
                _save_session(session_id, session)
                mark_check("repair_loop", True, f"approved on attempt {attempt_number}")
                log_event("repair.completed", session_id=session_id, status="approved", attempt=attempt_number)
                return session
            attempt["status"] = "review_rejected"
            failure_context = f"Reviewer rejected the patch: {verdict.get('reason', '')}"
            if rollback_on_failure:
                attempt["rollback"] = rollback_patch(str(patch_metadata["patch_id"]))
        except BudgetExceeded as exc:
            attempt["status"] = "budget_exhausted"
            attempt["error"] = str(exc)
            if patch_metadata and rollback_on_failure:
                try:
                    attempt["rollback"] = rollback_patch(str(patch_metadata["patch_id"]))
                except Exception as rollback_exc:
                    attempt["rollback_error"] = str(rollback_exc)
                    session["status"] = "rollback_blocked"
                    session["completed_at"] = _now()
                    _save_session(session_id, session)
                    raise RuntimeError(f"repair rollback blocked: {rollback_exc}") from rollback_exc
            attempt["completed_at"] = _now()
            session["status"] = "budget_exhausted"
            session["budget"] = {**budget.snapshot(), "reason": str(exc)}
            session["completed_at"] = _now()
            _save_session(session_id, session)
            mark_check("repair_loop", False, str(exc))
            log_event("repair.completed", session_id=session_id, status="budget_exhausted", reason=str(exc))
            return session
        except Exception as exc:
            attempt["status"] = "error"
            attempt["error"] = str(exc)
            failure_context = f"Repair attempt failed before approval: {exc}"
            if patch_metadata and rollback_on_failure:
                try:
                    attempt["rollback"] = rollback_patch(str(patch_metadata["patch_id"]))
                except Exception as rollback_exc:
                    attempt["rollback_error"] = str(rollback_exc)
                    attempt["completed_at"] = _now()
                    session["status"] = "rollback_blocked"
                    session["completed_at"] = _now()
                    _save_session(session_id, session)
                    mark_check("repair_loop", False, f"rollback blocked: {rollback_exc}")
                    raise RuntimeError(f"repair rollback blocked: {rollback_exc}") from rollback_exc
        attempt["completed_at"] = _now()
        _save_session(session_id, session)

    session["status"] = "attempts_exhausted"
    session["budget"] = budget.snapshot()
    session["completed_at"] = _now()
    _save_session(session_id, session)
    mark_check("repair_loop", False, f"{attempts_limit} attempt(s) exhausted")
    log_event("repair.completed", session_id=session_id, status="attempts_exhausted")
    return session


def load_repair_session(session_id: str = "latest", *, root: Path | None = None) -> dict[str, object]:
    project_root = ROOT if root is None else root
    if session_id == "latest":
        text = read_latest_session(f"{REPAIR_ROOT}/latest.json", REPAIR_ROOT, "")
        path = project_root / REPAIR_ROOT / "latest.json"
    else:
        if not _REPAIR_ID.fullmatch(session_id):
            raise ValueError("invalid repair session id")
        path = project_root / REPAIR_ROOT / session_id / "session.json"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text:
        raise ValueError(f"repair session not found: {session_id}")
    try:
        session = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid repair session JSON: {session_id}") from exc
    if not isinstance(session, dict):
        raise ValueError(f"invalid repair session: {session_id}")
    stored_id = str(session.get("session_id", ""))
    if not _REPAIR_ID.fullmatch(stored_id):
        raise ValueError("repair session id is invalid")
    if session_id != "latest" and stored_id != session_id:
        raise ValueError("repair session id does not match its checkpoint path")
    format_version = session.get("format_version", 1)
    if not isinstance(format_version, int) or isinstance(format_version, bool) or format_version not in {1, 2}:
        raise ValueError("repair session format version is unsupported")
    if format_version == 2 and session.get("session_sha256") != repair_session_sha256(session):
        raise ValueError("repair session provenance hash mismatch")
    status = str(session.get("status", ""))
    allowed_statuses = {
        "running", "approved", "already_verified", "attempts_exhausted", "budget_exhausted",
        "rollback_blocked", "abandoned", "resumed", "superseded",
    }
    if status not in allowed_statuses:
        raise ValueError(f"repair session status is invalid: {status or 'missing'}")
    attempts = session.get("attempts", [])
    if not isinstance(attempts, list) or not all(isinstance(attempt, dict) for attempt in attempts):
        raise ValueError("repair session attempts must be a list of JSON objects")
    if any(attempt.get("attempt") != index for index, attempt in enumerate(attempts, start=1)):
        raise ValueError("repair session attempt sequence is inconsistent")
    if status == "approved" and format_version == 2:
        approved = [attempt for attempt in attempts if attempt.get("status") == "approved"]
        if len(approved) != 1:
            raise ValueError("approved repair session must contain exactly one approved attempt")
        stored = approved[0].get("review_provenance_sha256")
        if stored != review_provenance_sha256(approved[0]):
            raise ValueError("approved repair review provenance hash mismatch")
    return session


def _restored_budget(session: dict[str, object], policy: dict[str, object]) -> RunBudget:
    snapshot = session.get("budget", {})
    if not isinstance(snapshot, dict):
        raise ValueError("repair session budget must be a JSON object")
    try:
        elapsed = float(snapshot.get("elapsed_seconds", 0.0))
        ai_calls = int(snapshot.get("ai_calls", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("repair session budget usage is invalid") from exc
    if elapsed < 0 or ai_calls < 0:
        raise ValueError("repair session budget usage cannot be negative")
    return RunBudget(
        max_elapsed_seconds=_bounded_int(policy, "max_elapsed_seconds", 1800, 10, 86400),
        max_ai_calls=_bounded_int(policy, "max_ai_calls", 12, 1, 100),
        initial_elapsed_seconds=elapsed,
        initial_ai_calls=ai_calls,
    )


def _attempt_patch_id(attempt: dict[str, object]) -> str:
    patch_data = attempt.get("patch", {})
    if not isinstance(patch_data, dict):
        raise ValueError("repair attempt patch metadata must be a JSON object")
    patch_id = str(patch_data.get("patch_id", ""))
    if not patch_id:
        raise ValueError("repair attempt patch metadata is missing patch_id")
    return patch_id


def _rollback_attempt(session: dict[str, object], attempt: dict[str, object]) -> None:
    if attempt.get("rollback") or not attempt.get("patch"):
        return
    patch_id = _attempt_patch_id(attempt)
    try:
        attempt["rollback"] = rollback_patch(patch_id)
    except ValueError as exc:
        if "already rolled back" in str(exc):
            attempt["rollback"] = {"patch_id": patch_id, "rolled_back": True, "already_rolled_back": True}
            return
        attempt["rollback_error"] = str(exc)
        session["status"] = "rollback_blocked"
        session["completed_at"] = _now()
        _save_session(str(session["session_id"]), session)
        mark_check("repair_loop", False, f"rollback blocked: {exc}")
        raise ResumeBlocked(f"repair resume rollback blocked: {exc}") from exc


def _complete_resumed_approval(session: dict[str, object], attempt: dict[str, object]) -> dict[str, object]:
    attempt["status"] = "approved"
    attempt["review_provenance_sha256"] = review_provenance_sha256(attempt)
    attempt["completed_at"] = attempt.get("completed_at") or _now()
    session["status"] = "approved"
    session["completed_at"] = _now()
    session["resumed_at"] = _now()
    _save_session(str(session["session_id"]), session)
    mark_check("repair_loop", True, f"approved on resumed attempt {attempt.get('attempt')}")
    log_event("repair.completed", session_id=session["session_id"], status="approved", attempt=attempt.get("attempt"), resumed=True)
    return session


def _finalize_saved_approval(session: dict[str, object], attempt: dict[str, object]) -> None:
    try:
        policy = load_repair_policy()
        _enforce_review_independence(policy)
        _enforce_actual_review_independence(policy, attempt)
        enforce_decision_gate("reviewer")
    except Exception as exc:
        _rollback_attempt(session, attempt)
        attempt["status"] = "stale_approval_rolled_back" if attempt.get("rollback") else "approval_blocked"
        attempt["error"] = str(exc)
        attempt["completed_at"] = _now()
        _save_session(str(session["session_id"]), session)
        mark_check("repair_loop", False, "saved reviewer approval is stale")
        log_event(
            "repair.saved_approval.blocked",
            session_id=session["session_id"],
            attempt=attempt.get("attempt"),
            rolled_back=bool(attempt.get("rollback")),
        )
        raise
    _complete_resumed_approval(session, attempt)


def _resume_inflight_attempt(
    session: dict[str, object],
    attempt: dict[str, object],
    *,
    retries: int,
) -> str:
    session_id = str(session["session_id"])
    task = str(session.get("task", "")).strip()
    if not task:
        raise ValueError("repair session task is missing")
    attempt_number = int(attempt.get("attempt", 0))
    if attempt_number < 1:
        raise ValueError("repair attempt number is invalid")
    reviewer = attempt.get("reviewer")
    if isinstance(reviewer, dict) and reviewer.get("approved") is True:
        _finalize_saved_approval(session, attempt)
        return "approved"

    enforce_decision_gate("coder")
    policy = load_repair_policy()
    _enforce_review_independence(policy)
    rollback_on_failure = bool(policy.get("rollback_on_failure", True))
    reuse_ai_responses = bool(policy.get("reuse_ai_responses", True))
    cache_max_age = _bounded_int(policy, "ai_cache_max_age_seconds", 86400, 60, 604800)
    ai_max_tokens = _bounded_int(policy, "ai_max_tokens", 4096, 128, 32768)
    budget = _restored_budget(session, policy)
    initial_verification = session.get("initial_verification", {})
    if not isinstance(initial_verification, dict):
        raise ValueError("repair session initial_verification must be a JSON object")
    failure_context = _failure_summary(initial_verification)
    decision = read_text("docs/03-decision-record.md", "")[-12000:]
    diff_path = f"{REPAIR_ROOT}/{session_id}/attempt-{attempt_number}.diff"
    diff = read_text(diff_path, "")

    try:
        patch_data = attempt.get("patch")
        if patch_data:
            patch_id = _attempt_patch_id(attempt)
            state = patch_state(patch_id)
            if state["state"] == "rolled_back":
                attempt["rollback"] = {"patch_id": patch_id, "rolled_back": True, "already_rolled_back": True}
                attempt["status"] = "interrupted_rolled_back"
                attempt["completed_at"] = _now()
                _save_session(session_id, session)
                return "continue"
            if state["state"] != "applied":
                conflicts = ", ".join(str(item) for item in state.get("conflicts", []))
                raise ResumeBlocked(f"repair resume patch state conflict: {conflicts}")
            if not diff:
                diff = read_text(f"{PATCH_ROOT}/{patch_id}/patch.diff", "")

        if not patch_data:
            if not diff:
                diagnosis = attempt.get("debugger")
                if not isinstance(diagnosis, dict):
                    budget.reserve_ai_call("debugger")
                    session["budget"] = budget.snapshot()
                    result = invoke_cached(
                        "debugger",
                        _debugger_prompt(task, failure_context),
                        max_tokens=ai_max_tokens,
                        retries=retries,
                        enabled=reuse_ai_responses,
                        max_age_seconds=cache_max_age,
                    )
                    budget.check("debugger response processing")
                    diagnosis = parse_json_response(str(result.get("content", "")), "debugger")
                    attempt["debugger"] = diagnosis
                    _save_session(session_id, session)
                file_context = collect_file_context(diagnosis.get("files", []), policy)
                budget.reserve_ai_call("coder")
                session["budget"] = budget.snapshot()
                result = invoke_cached(
                    "coder",
                    _coder_prompt(task, decision, diagnosis, file_context, failure_context),
                    max_tokens=ai_max_tokens,
                    retries=retries,
                    enabled=reuse_ai_responses,
                    max_age_seconds=cache_max_age,
                )
                _record_invocation_service(attempt, "coder", result)
                budget.check("coder response processing")
                diff = extract_unified_diff(str(result.get("content", "")))
                write_text(diff_path, diff)
                attempt["diff_file"] = diff_path
                _save_session(session_id, session)
            patch_data = apply_patch_text(diff)
            attempt["patch"] = patch_data
            _save_session(session_id, session)

        verification = attempt.get("verification")
        if not isinstance(verification, dict):
            verification = run_verification_commands()
            budget.check(f"resumed attempt {attempt_number} review")
            attempt["verification"] = verification
            session["budget"] = budget.snapshot()
            _save_session(session_id, session)
        if not verification.get("passed"):
            attempt["status"] = "verification_failed"
            if rollback_on_failure:
                _rollback_attempt(session, attempt)
            attempt["completed_at"] = _now()
            _save_session(session_id, session)
            return "continue"

        if not diff:
            raise ValueError("resumed repair attempt is missing its patch diff")
        verdict = attempt.get("reviewer")
        if not isinstance(verdict, dict):
            budget.reserve_ai_call("reviewer")
            session["budget"] = budget.snapshot()
            enforce_decision_gate("reviewer")
            result = invoke_cached(
                "reviewer",
                _reviewer_prompt(task, diff, verification),
                max_tokens=ai_max_tokens,
                retries=retries,
                enabled=reuse_ai_responses,
                max_age_seconds=cache_max_age,
            )
            _record_invocation_service(attempt, "reviewer", result)
            budget.check("reviewer response processing")
            verdict = parse_json_response(str(result.get("content", "")), "reviewer")
            attempt["reviewer"] = verdict
            _save_session(session_id, session)
        if not isinstance(verdict.get("approved"), bool):
            raise ValueError("reviewer approved must be a boolean")
        if verdict["approved"]:
            _enforce_actual_review_independence(policy, attempt)
            enforce_decision_gate("reviewer")
            session["budget"] = budget.snapshot()
            _complete_resumed_approval(session, attempt)
            return "approved"
        attempt["status"] = "review_rejected"
        if rollback_on_failure:
            _rollback_attempt(session, attempt)
        attempt["completed_at"] = _now()
        session["budget"] = budget.snapshot()
        _save_session(session_id, session)
        return "continue"
    except BudgetExceeded as exc:
        attempt["status"] = "budget_exhausted"
        attempt["error"] = str(exc)
        if attempt.get("patch") and rollback_on_failure:
            _rollback_attempt(session, attempt)
        attempt["completed_at"] = _now()
        session["status"] = "budget_exhausted"
        session["budget"] = {**budget.snapshot(), "reason": str(exc)}
        session["completed_at"] = _now()
        _save_session(session_id, session)
        mark_check("repair_loop", False, str(exc))
        log_event("repair.completed", session_id=session_id, status="budget_exhausted", reason=str(exc), resumed=True)
        return "budget_exhausted"
    except ResumeBlocked as exc:
        session["status"] = "rollback_blocked"
        session["resume_error"] = str(exc)
        session["completed_at"] = _now()
        _save_session(session_id, session)
        mark_check("repair_loop", False, str(exc))
        raise
    except Exception as exc:
        attempt["status"] = "error"
        attempt["error"] = str(exc)
        if attempt.get("patch") and rollback_on_failure:
            _rollback_attempt(session, attempt)
        attempt["completed_at"] = _now()
        session["budget"] = budget.snapshot()
        _save_session(session_id, session)
        return "continue"


def resume_repair_loop(session_id: str, *, retries: int = 1) -> dict[str, object]:
    resolved_id = str(load_repair_session(session_id)["session_id"]) if session_id == "latest" else session_id
    with operation_lock("repair", resolved_id):
        return _resume_repair_loop_unlocked(resolved_id, retries=retries)


def abandon_repair_loop(session_id: str, reason: str) -> dict[str, object]:
    resolved_id = str(load_repair_session(session_id)["session_id"]) if session_id == "latest" else session_id
    with operation_lock("repair", resolved_id):
        return _abandon_repair_loop_unlocked(resolved_id, reason)


def _abandon_repair_loop_unlocked(session_id: str, reason: str) -> dict[str, object]:
    session = load_repair_session(session_id)
    status = str(session.get("status", ""))
    if status in {"approved", "already_verified"}:
        raise ValueError(f"successful repair session cannot be abandoned: {status}")
    if status == "superseded":
        return session
    if status == "abandoned":
        return session
    reason = reason.strip()
    if not reason:
        raise ValueError("repair abandonment reason is required")
    if len(reason) > 1000:
        raise ValueError("repair abandonment reason must not exceed 1000 characters")
    attempts = session.get("attempts", [])
    if not isinstance(attempts, list):
        raise ValueError("repair session attempts must be a list")
    if attempts:
        latest = attempts[-1]
        if not isinstance(latest, dict):
            raise ValueError("repair session attempt must be a JSON object")
        if latest.get("patch") and not latest.get("rollback"):
            _rollback_attempt(session, latest)
    session["status"] = "abandoned"
    session["abandonment_reason"] = reason
    session["abandoned_at"] = _now()
    session["completed_at"] = session["abandoned_at"]
    _save_session(session_id, session)
    mark_check("repair_loop", False, f"{session_id}: abandoned")
    log_event(
        "repair.abandoned",
        session_id=session_id,
        attempts=len(attempts),
        reason_sha256=hashlib.sha256(reason.encode("utf-8")).hexdigest(),
    )
    return session


def _resume_repair_loop_unlocked(session_id: str, *, retries: int = 1) -> dict[str, object]:
    session = load_repair_session(session_id)
    status = str(session.get("status", ""))
    if status in {"approved", "already_verified", "attempts_exhausted", "budget_exhausted"}:
        return session
    if status == "abandoned":
        raise RuntimeError("repair session is terminal: abandoned")
    if status == "superseded":
        raise RuntimeError("repair session is terminal: superseded")
    if status not in {"running", "rollback_blocked"}:
        raise ValueError(f"repair session cannot be resumed from status: {status}")

    attempts = session.get("attempts", [])
    if not isinstance(attempts, list):
        raise ValueError("repair session attempts must be a list")
    if attempts:
        latest = attempts[-1]
        if not isinstance(latest, dict):
            raise ValueError("repair session attempt must be a JSON object")
        if latest.get("status") == "running" or status == "rollback_blocked":
            log_event("repair.resume.started", session_id=session_id, attempt=latest.get("attempt"))
            outcome = _resume_inflight_attempt(session, latest, retries=retries)
            log_event("repair.resume.completed", session_id=session_id, attempt=latest.get("attempt"), outcome=outcome)
            if outcome in {"approved", "budget_exhausted"}:
                return session

    original_budget = int(session.get("max_attempts", 1))
    remaining = max(0, original_budget - len(attempts))
    if remaining == 0:
        session["status"] = "attempts_exhausted"
        session["completed_at"] = _now()
        _save_session(str(session.get("session_id", session_id)), session)
        mark_check("repair_loop", False, "no attempt budget remains after resume recovery")
        return session
    session["status"] = "resumed"
    session["completed_at"] = _now()
    _save_session(str(session.get("session_id", session_id)), session)
    successor = run_repair_loop(
        str(session.get("task", "")),
        max_attempts=remaining,
        retries=retries,
        resumed_from=str(session.get("session_id", session_id)),
    )
    successor_id = str(successor.get("session_id", ""))
    if successor_id:
        session["status"] = "superseded"
        session["successor_session_id"] = successor_id
        session["superseded_at"] = _now()
        _save_session_original(str(session.get("session_id", session_id)), session)
    return successor
