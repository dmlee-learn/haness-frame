from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from . import storage
from .debate import load_debate_session
from .orchestration import PLANNING_SYSTEM, load_orchestration_execution
from .repair import load_repair_session
from .workflow import load_pipeline_session

SESSION_ROOTS = {
    "orchestration": "workspace/orchestration/executions",
    "pipeline": "workspace/executions/runs",
    "debate": "workspace/debates",
    "repair": "workspace/repairs",
}
RESOLVED_STATUSES = {
    "orchestration": {"completed", "abandoned"},
    "pipeline": {"completed", "abandoned"},
    "debate": {"completed", "abandoned"},
    "repair": {"approved", "already_verified", "abandoned", "superseded"},
}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _orchestration_child_status(payload: dict[str, object]) -> str:
    link = payload.get("linked_session", {})
    if not isinstance(link, dict):
        return ""
    child_kind = str(link.get("kind", ""))
    child_id = str(link.get("id", ""))
    roots = {
        "pipeline": "workspace/executions/runs",
        "debate": "workspace/debates",
        "repair": "workspace/repairs",
    }
    if child_kind not in roots or not SAFE_ID.fullmatch(child_id):
        return ""
    path = storage.ROOT / roots[child_kind] / child_id / "session.json"
    try:
        child = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(child.get("status", "")) if isinstance(child, dict) else ""


def _validate_terminal_orchestration_child(payload: dict[str, object]) -> None:
    wrapper_status = str(payload.get("status", ""))
    if wrapper_status not in {"completed", "abandoned"}:
        return
    link = payload.get("linked_session")
    if not isinstance(link, dict):
        raise ValueError("terminal orchestration child link is invalid")
    kind = str(link.get("kind", ""))
    child_id = str(link.get("id", ""))
    linked_status = str(link.get("status", ""))
    if wrapper_status == "abandoned" and linked_status == "not_started":
        return
    paths = {
        "pipeline": "workspace/executions/runs",
        "debate": "workspace/debates",
        "repair": "workspace/repairs",
    }
    root = paths.get(kind)
    if root is None or not SAFE_ID.fullmatch(child_id):
        raise ValueError("terminal orchestration child identity is invalid")
    path = storage.ROOT / root / child_id / "session.json"
    if not path.is_file():
        raise ValueError(f"terminal orchestration child checkpoint is missing: {kind}/{child_id}")
    if kind == "pipeline":
        child = load_pipeline_session(child_id)
    elif kind == "debate":
        child = load_debate_session(child_id)
    else:
        child = load_repair_session(child_id, root=storage.ROOT)
    actual_status = str(child.get("status", ""))
    if actual_status != linked_status:
        raise ValueError(
            f"terminal orchestration child status mismatch: linked {linked_status}, actual {actual_status}"
        )
    if kind == "debate":
        child_task_sha = str(child.get("prompt_sha256", ""))
    else:
        field = "prompt" if kind == "pipeline" else "task"
        child_task_sha = hashlib.sha256(str(child.get(field, "")).encode("utf-8")).hexdigest()
    if child_task_sha != str(payload.get("task_sha256", "")):
        raise ValueError("terminal orchestration child input hash does not match its wrapper")
    wrapper_roles = payload.get("roles")
    if kind in {"pipeline", "debate"} and child.get("roles") != wrapper_roles:
        raise ValueError("terminal orchestration child roles do not match its wrapper")
    wrapper_options = payload.get("options", {})
    child_options = child.get("options", {})
    if not isinstance(wrapper_options, dict) or not isinstance(child_options, dict):
        raise ValueError("terminal orchestration child options are invalid")
    if kind == "pipeline" and child.get("system") != PLANNING_SYSTEM:
        raise ValueError("terminal orchestration pipeline system contract does not match")
    if kind in {"pipeline", "debate"} and child_options.get("retries") != wrapper_options.get("retries"):
        raise ValueError("terminal orchestration child retry contract does not match")
    if kind == "debate" and child.get("rounds_requested") != wrapper_options.get("rounds"):
        raise ValueError("terminal orchestration debate round contract does not match")
    if kind == "repair":
        actual_attempts = child.get("max_attempts")
        requested_attempts = wrapper_options.get("max_attempts")
        if (
            isinstance(actual_attempts, bool)
            or not isinstance(actual_attempts, int)
            or not 1 <= actual_attempts <= 10
        ):
            raise ValueError("terminal orchestration repair attempt contract is invalid")
        if requested_attempts is not None and actual_attempts > requested_attempts:
            raise ValueError("terminal orchestration repair attempt contract exceeds its wrapper")


def _next_action(kind: str, session_id: str, status: str, payload: dict[str, object]) -> str:
    if status in RESOLVED_STATUSES[kind]:
        return ""
    if not SAFE_ID.fullmatch(session_id):
        return "Inspect the checkpoint manually because its session ID is unsafe."
    if kind == "orchestration":
        link = payload.get("linked_session", {})
        linked_status = str(link.get("status", "")) if isinstance(link, dict) else ""
        child_status = _orchestration_child_status(payload)
        terminal = {
            "pipeline": {"completed", "abandoned", "budget_exhausted"},
            "debate": {"completed", "abandoned", "stale", "budget_exhausted"},
            "repair": {
                "approved", "already_verified", "abandoned", "superseded",
                "attempts_exhausted", "budget_exhausted", "rollback_blocked",
            },
        }
        child_kind = str(link.get("kind", "")) if isinstance(link, dict) else ""
        resolved_child = {"completed", "approved", "already_verified", "abandoned", "superseded"}
        if child_status in resolved_child:
            return f"python app.py orchestrate-reconcile --id {session_id}"
        if child_status in terminal.get(child_kind, set()) and child_status != linked_status:
            return f"python app.py orchestrate-reconcile --id {session_id}"
        terminal_failures = {
            "budget_exhausted", "stale", "attempts_exhausted", "rollback_blocked"
        }
        if child_status in terminal_failures and child_status == linked_status:
            return f'python app.py orchestrate-abandon --id {session_id} --reason "Superseded orchestration"'
        return f"python app.py orchestrate-resume --id {session_id}"
    if kind == "pipeline":
        if status == "budget_exhausted":
            return f'python app.py pipeline-abandon --id {session_id} --reason "Superseded run"'
        return f"python app.py pipeline-resume --id {session_id}"
    if kind == "debate":
        if status in {"budget_exhausted", "stale"}:
            return f'python app.py debate-abandon --id {session_id} --reason "Superseded debate"'
        return f"python app.py debate-resume --id {session_id}"
    if status in {"budget_exhausted", "attempts_exhausted", "rollback_blocked"}:
        return f'python app.py repair-abandon --id {session_id} --reason "Superseded repair"'
    return f"python app.py repair-resume --id {session_id}"


def _progress(kind: str, payload: dict[str, object]) -> dict[str, object]:
    if kind == "orchestration":
        roles = payload.get("roles", [])
        return {
            "stage": payload.get("stage", ""),
            "roles": len(roles) if isinstance(roles, list) else 0,
            "linked_session": payload.get("linked_session", {}),
        }
    if kind == "pipeline":
        roles = payload.get("roles", [])
        results = payload.get("results", [])
        return {
            "completed_roles": len(results) if isinstance(results, list) else 0,
            "total_roles": len(roles) if isinstance(roles, list) else 0,
        }
    if kind == "debate":
        rounds = payload.get("round_results", [])
        return {
            "stage": payload.get("stage", ""),
            "completed_rounds": len(rounds) if isinstance(rounds, list) else 0,
            "requested_rounds": payload.get("rounds_requested", 0),
        }
    attempts = payload.get("attempts", [])
    return {"attempts": len(attempts) if isinstance(attempts, list) else 0}


def _summarize(kind: str, path: Path) -> dict[str, object]:
    session_id = path.parent.name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("session root must be a JSON object")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "kind": kind,
            "id": session_id,
            "status": "invalid_checkpoint",
            "updated_at": "",
            "needs_attention": True,
            "failure_reason": str(exc)[:500],
            "progress": {},
            "next_action": f"Inspect {path.relative_to(storage.ROOT).as_posix()} and restore a valid checkpoint.",
            "_sort": path.stat().st_mtime if path.exists() else 0.0,
        }
    id_field = "execution_id" if kind == "orchestration" else ("run_id" if kind == "pipeline" else "session_id")
    stored_id = str(payload.get(id_field, session_id))
    if stored_id != session_id:
        status = "invalid_checkpoint"
        return {
            "kind": kind,
            "id": session_id,
            "status": status,
            "updated_at": "",
            "needs_attention": True,
            "failure_reason": "stored session ID does not match its directory",
            "progress": {},
            "next_action": f"Inspect {path.relative_to(storage.ROOT).as_posix()} and restore a valid checkpoint.",
            "_sort": path.stat().st_mtime,
        }
    if kind in {"orchestration", "pipeline", "debate", "repair"}:
        try:
            if kind == "orchestration":
                payload = load_orchestration_execution(session_id)
                _validate_terminal_orchestration_child(payload)
            elif kind == "pipeline":
                payload = load_pipeline_session(session_id)
            elif kind == "debate":
                payload = load_debate_session(session_id)
            else:
                payload = load_repair_session(session_id, root=storage.ROOT)
        except ValueError as exc:
            return {
                "kind": kind,
                "id": session_id,
                "status": "invalid_checkpoint",
                "updated_at": "",
                "needs_attention": True,
                "failure_reason": str(exc)[:500],
                "progress": {},
                "next_action": f"Inspect {path.relative_to(storage.ROOT).as_posix()} and restore a valid checkpoint.",
                "_sort": path.stat().st_mtime,
            }
    status = str(payload.get("status", "unknown"))
    updated_at = str(payload.get("updated_at") or payload.get("completed_at") or payload.get("created_at") or "")
    return {
        "kind": kind,
        "id": stored_id,
        "status": status,
        "updated_at": updated_at,
        "needs_attention": status not in RESOLVED_STATUSES[kind],
        "failure_reason": str(payload.get("error", ""))[:500],
        "progress": _progress(kind, payload),
        "next_action": _next_action(kind, stored_id, status, payload),
        "_sort": _timestamp(updated_at, path),
    }


def _timestamp(value: str, path: Path) -> float:
    if value:
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return path.stat().st_mtime


def session_overview(*, limit: int = 20, unresolved_only: bool = False) -> dict[str, object]:
    if isinstance(limit, bool) or limit < 1 or limit > 200:
        raise ValueError("session overview limit must be between 1 and 200")
    sessions: list[dict[str, object]] = []
    for kind, relative_root in SESSION_ROOTS.items():
        root = storage.ROOT / relative_root
        if root.is_dir():
            sessions.extend(_summarize(kind, path) for path in root.glob("*/session.json"))
    sessions.sort(key=lambda item: float(item["_sort"]), reverse=True)
    total = len(sessions)
    attention = sum(bool(item["needs_attention"]) for item in sessions)
    if unresolved_only:
        sessions = [item for item in sessions if item["needs_attention"]]
    selected = sessions[:limit]
    for item in selected:
        item.pop("_sort", None)
    return {
        "generated_at": _now(),
        "total_sessions": total,
        "needs_attention": attention,
        "unresolved_only": unresolved_only,
        "returned": len(selected),
        "sessions": selected,
    }
