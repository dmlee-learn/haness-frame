from __future__ import annotations

import datetime as dt
import json

from .storage import ROOT, ensure_workspace, read_text

AUDIT_LOG = "workspace/logs/audit.jsonl"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def log_event(event: str, **fields: object) -> dict[str, object]:
    ensure_workspace()
    record = {"created_at": _now(), "event": event, **fields}
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    path = ROOT / AUDIT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")
    return record


def recent_events(limit: int = 20) -> list[dict[str, object]]:
    payload = read_text(AUDIT_LOG, "")
    records: list[dict[str, object]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records[-limit:]
