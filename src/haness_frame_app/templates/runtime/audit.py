from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from .storage import ROOT, ensure_workspace, file_lock, read_text, write_path_text

AUDIT_LOG = "workspace/logs/audit.jsonl"
AUDIT_FORMAT_VERSION = 2


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _record_sha256(record: dict[str, object]) -> str:
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _latest_chain_hash(payload: str) -> str:
    for line in reversed(payload.splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(record, dict)
            and record.get("format_version") == AUDIT_FORMAT_VERSION
            and isinstance(record.get("record_sha256"), str)
        ):
            return str(record["record_sha256"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_event(event: str, **fields: object) -> dict[str, object]:
    ensure_workspace()
    path = ROOT / AUDIT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        separator = "\n" if existing and not existing.endswith("\n") else ""
        chain_prefix = existing + separator
        record = {
            **fields,
            "format_version": AUDIT_FORMAT_VERSION,
            "created_at": _now(),
            "event": event,
            "previous_sha256": _latest_chain_hash(chain_prefix),
        }
        record["record_sha256"] = _record_sha256(record)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(separator)
            handle.write(f"{line}\n")
            handle.flush()
            os.fsync(handle.fileno())
    return record


def inspect_audit_log() -> dict[str, object]:
    payload = read_text(AUDIT_LOG, "")
    records: list[dict[str, object]] = []
    issues: list[str] = []
    event_counts: dict[str, int] = {}
    legacy_prefix = ""
    chain_started = False
    previous_hash = ""
    for line_number, raw_line in enumerate(payload.splitlines(keepends=True), start=1):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            if not chain_started:
                legacy_prefix += raw_line
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"line {line_number}: invalid JSON: {exc.msg}")
            if not chain_started:
                legacy_prefix += raw_line
            continue
        if not isinstance(record, dict):
            issues.append(f"line {line_number}: record must be a JSON object")
            if not chain_started:
                legacy_prefix += raw_line
            continue
        if record.get("format_version") == AUDIT_FORMAT_VERSION:
            expected_previous = (
                previous_hash
                if chain_started
                else hashlib.sha256(legacy_prefix.encode("utf-8")).hexdigest()
            )
            if record.get("previous_sha256") != expected_previous:
                issues.append(f"line {line_number}: audit previous hash mismatch")
            stored_hash = record.get("record_sha256")
            if not isinstance(stored_hash, str) or stored_hash != _record_sha256(record):
                issues.append(f"line {line_number}: audit record hash mismatch")
            chain_started = True
            previous_hash = str(stored_hash or "")
        elif chain_started:
            issues.append(f"line {line_number}: unchained record after audit chain started")
        else:
            legacy_prefix += raw_line
        event = record.get("event")
        created_at = record.get("created_at")
        if not isinstance(event, str) or not event.strip():
            issues.append(f"line {line_number}: event must be a non-empty string")
        if not isinstance(created_at, str):
            issues.append(f"line {line_number}: created_at must be an ISO-8601 string")
        else:
            try:
                timestamp = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("timezone is required")
            except ValueError as exc:
                issues.append(f"line {line_number}: invalid created_at: {exc}")
        records.append(record)
        if isinstance(event, str) and event.strip():
            event_counts[event] = event_counts.get(event, 0) + 1
    return {
        "valid": not issues,
        "record_count": len(records),
        "first_created_at": records[0].get("created_at") if records else None,
        "last_created_at": records[-1].get("created_at") if records else None,
        "event_counts": dict(sorted(event_counts.items())),
        "issues": issues,
        "records": records,
    }


def recent_events(limit: int = 20) -> list[dict[str, object]]:
    if limit < 1 or limit > 10000:
        raise ValueError("audit limit must be between 1 and 10000")
    records = inspect_audit_log()["records"]
    assert isinstance(records, list)
    return records[-limit:]


def audit_check() -> dict[str, object]:
    report = inspect_audit_log()
    return {key: value for key, value in report.items() if key != "records"}


def export_audit(filename: str = "") -> Path:
    ensure_workspace()
    reports_dir = ROOT / "workspace" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if filename:
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("audit export filename must be a plain file name")
        name = filename
    else:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S%f")
        name = f"audit-{stamp}.json"
    if not name.lower().endswith(".json"):
        raise ValueError("audit export filename must end with .json")
    path = reports_dir / name
    report = inspect_audit_log()
    export = {
        "format": "haness-frame-audit-export",
        "format_version": 1,
        "generated_at": _now(),
        "source": AUDIT_LOG,
        **report,
    }
    write_path_text(path, json.dumps(export, indent=2, ensure_ascii=False))
    log_event("audit.exported", path=str(path), record_count=report["record_count"], valid=report["valid"])
    return path
