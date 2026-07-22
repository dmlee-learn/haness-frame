from __future__ import annotations

import datetime as dt

from . import storage
from .audit import log_event
from .orchestration import (
    EXECUTION_ROOT,
    _child_checkpoint_exists,
    _load_child_session,
    load_orchestration_execution,
    reconcile_orchestration_execution,
)

TERMINAL_CHILD_STATUSES = {
    "pipeline": {"completed", "abandoned", "budget_exhausted"},
    "debate": {"completed", "abandoned", "stale", "budget_exhausted"},
    "repair": {
        "approved",
        "already_verified",
        "abandoned",
        "superseded",
        "attempts_exhausted",
        "budget_exhausted",
        "rollback_blocked",
    },
}


def reconcile_orchestration_executions(*, limit: int = 100) -> dict[str, object]:
    if isinstance(limit, bool) or limit < 1 or limit > 200:
        raise ValueError("orchestration reconcile limit must be between 1 and 200")
    root = storage.ROOT / EXECUTION_ROOT
    paths = sorted(
        root.glob("*/session.json") if root.is_dir() else [],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    reconciled: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    skipped = {"resolved": 0, "active": 0, "missing_child": 0}
    for path in paths:
        execution_id = path.parent.name
        try:
            execution = load_orchestration_execution(execution_id)
            if execution.get("status") in {"completed", "abandoned"}:
                skipped["resolved"] += 1
                continue
            link = execution.get("linked_session", {})
            if not isinstance(link, dict):
                raise ValueError("orchestration execution child link is invalid")
            kind = str(link.get("kind", ""))
            child_id = str(link.get("id", ""))
            if not child_id or not _child_checkpoint_exists(kind, child_id):
                skipped["missing_child"] += 1
                continue
            child_status = str(_load_child_session(kind, child_id).get("status", ""))
            if child_status not in TERMINAL_CHILD_STATUSES.get(kind, set()):
                skipped["active"] += 1
                continue
            updated = reconcile_orchestration_execution(execution_id)
            reconciled.append({"execution_id": execution_id, "status": str(updated.get("status", ""))})
        except Exception as exc:
            failures.append({"execution_id": execution_id, "error_type": type(exc).__name__})
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "scanned": len(paths),
        "reconciled": reconciled,
        "skipped": skipped,
        "failures": failures,
    }
    log_event(
        "orchestration.execution.reconcile_all",
        scanned=len(paths),
        reconciled=len(reconciled),
        failures=len(failures),
    )
    return report
