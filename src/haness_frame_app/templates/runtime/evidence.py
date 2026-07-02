from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .audit import log_event
from .scorecard import mark_check
from .storage import ensure_workspace, read_text, write_text

EVIDENCE_JSON = "workspace/evidence/search-evidence.json"
EVIDENCE_MD = "research/search-evidence.md"
EVIDENCE_DRAFT_MD = "research/search-evidence-draft.md"
EVIDENCE_GAPS_MD = "research/search-evidence-gaps.md"
SEARCH_PLAN_JSON = "workspace/evidence/search-plan.json"
REQUIRED_FIELDS = [
    "query",
    "provider",
    "url",
    "title",
    "excerpt",
    "retrieved_at",
    "confidence",
    "why_it_matters",
    "recommended_use",
]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _load_records() -> list[dict[str, str]]:
    ensure_workspace()
    payload = read_text(EVIDENCE_JSON, "[]")
    try:
        records = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def load_evidence() -> list[dict[str, str]]:
    return _load_records()


def _load_search_plan() -> dict[str, object]:
    payload = read_text(SEARCH_PLAN_JSON, "{}")
    try:
        plan = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return plan if isinstance(plan, dict) else {}


def evidence_draft_markdown() -> str:
    plan = _load_search_plan()
    searches = plan.get("searches", [])
    lines = ["# Search Evidence Draft", ""]
    if not isinstance(searches, list) or not searches:
        lines.extend(["No search plan found.", "", "Run `python app.py search-plan` first."])
        return "\n".join(lines) + "\n"
    for index, item in enumerate(searches, start=1):
        query = str(item.get("query", "")).strip() if isinstance(item, dict) else ""
        provider = str(item.get("provider", "")).strip() if isinstance(item, dict) else ""
        url = str(item.get("url", "")).strip() if isinstance(item, dict) else ""
        lines.extend(
            [
                f"## {index}. {query or 'Untitled'}",
                "",
                f"- query: {query}",
                f"- provider: {provider}",
                f"- url: {url}",
                "- title: ",
                "- excerpt: ",
                "- retrieved_at: ",
                "- confidence: ",
                "- why_it_matters: ",
                "- recommended_use: ",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_evidence_draft() -> str:
    return str(write_text(EVIDENCE_DRAFT_MD, evidence_draft_markdown()))


def evidence_gap_markdown() -> str:
    plan = _load_search_plan()
    searches = plan.get("searches", [])
    records = _load_records()
    lines = ["# Search Evidence Gaps", ""]
    if not isinstance(searches, list) or not searches:
        lines.extend(["No search plan found.", "", "Run `python app.py search-plan` first."])
        return "\n".join(lines) + "\n"
    covered = 0
    missing = []
    known_queries = {str(item.get("query", "") or "").strip() for item in records}
    known_urls = {str(item.get("url", "") or "").strip() for item in records}
    for item in searches:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        url = str(item.get("url", "")).strip()
        if query in known_queries or url in known_urls:
            covered += 1
            continue
        missing.append({"query": query, "url": url, "provider": str(item.get("provider", "")).strip()})
    lines.extend(
        [
            f"- planned searches: {len(searches)}",
            f"- covered searches: {covered}",
            f"- missing searches: {len(missing)}",
            "",
        ]
    )
    for index, item in enumerate(missing, start=1):
        lines.extend(
            [
                f"## {index}. {item['query'] or 'Untitled'}",
                "",
                f"- provider: {item['provider']}",
                f"- url: {item['url']}",
                "",
            ]
        )
    if not missing:
        lines.append("No evidence gaps remain.")
    return "\n".join(lines).rstrip() + "\n"


def write_evidence_gaps() -> str:
    return str(write_text(EVIDENCE_GAPS_MD, evidence_gap_markdown()))


def _parse_evidence_draft(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    key_map = {
        "query": "query",
        "provider": "provider",
        "url": "url",
        "title": "title",
        "excerpt": "excerpt",
        "retrieved_at": "retrieved_at",
        "confidence": "confidence",
        "why_it_matters": "why_it_matters",
        "recommended_use": "recommended_use",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if current:
                entries.append(current)
            current = {field: "" for field in REQUIRED_FIELDS}
            title = line[3:].strip()
            if ". " in title:
                title = title.split(". ", 1)[1].strip()
            current["title"] = title
            continue
        if current is None or not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        normalized = key_map.get(key.strip())
        if normalized:
            current[normalized] = value.strip()
    if current:
        entries.append(current)
    return entries


def commit_evidence_draft(path: str = EVIDENCE_DRAFT_MD) -> dict[str, object]:
    draft_path = Path(path)
    if not draft_path.exists():
        raise ValueError(f"evidence draft not found: {path}")
    entries = _parse_evidence_draft(draft_path.read_text(encoding="utf-8"))
    if not entries:
        raise ValueError("no evidence entries found in draft")
    committed: list[dict[str, str]] = []
    records = _load_records()
    existing_urls = {str(item.get("url", "") or "").strip() for item in records}
    for entry in entries:
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field, "").strip()]
        if missing:
            raise ValueError(f"draft entry missing fields: {', '.join(missing)}")
        if urlparse(entry["url"]).scheme not in {"http", "https", "file"}:
            raise ValueError(f"draft entry has invalid url: {entry['url']}")
        if entry["url"] in existing_urls:
            continue
        records.append(entry)
        committed.append(entry)
        existing_urls.add(entry["url"])
    if committed:
        save_evidence(records)
        mark_check("evidence", True, f"{len(records)} evidence record(s)")
        log_event("evidence.committed", count=len(committed))
    return {"committed": committed, "total": len(records)}


def save_evidence(records: list[dict[str, str]]) -> None:
    cleaned = []
    for record in records:
        cleaned.append({field: str(record.get(field, "") or "").strip() for field in REQUIRED_FIELDS})
    write_text(EVIDENCE_JSON, json.dumps(cleaned, indent=2, ensure_ascii=False))
    write_text(EVIDENCE_MD, evidence_markdown(cleaned))


def add_evidence(
    query: str,
    provider: str,
    url: str,
    title: str,
    excerpt: str,
    confidence: str,
    why_it_matters: str,
    recommended_use: str,
    retrieved_at: str = "",
) -> dict[str, str]:
    record = {
        "query": query.strip(),
        "provider": provider.strip(),
        "url": url.strip(),
        "title": title.strip(),
        "excerpt": excerpt.strip(),
        "retrieved_at": retrieved_at.strip() or _now(),
        "confidence": confidence.strip(),
        "why_it_matters": why_it_matters.strip(),
        "recommended_use": recommended_use.strip(),
    }
    missing = [field for field in REQUIRED_FIELDS if not record.get(field)]
    if missing:
        raise ValueError(f"missing evidence fields: {', '.join(missing)}")
    if urlparse(record["url"]).scheme not in {"http", "https", "file"}:
        raise ValueError("evidence url must start with http://, https://, or file://")
    records = _load_records()
    if any(str(item.get("url", "") or "").strip() == record["url"] for item in records):
        raise ValueError(f"duplicate evidence url: {record['url']}")
    records.append(record)
    save_evidence(records)
    mark_check("evidence", True, f"{len(records)} evidence record(s)")
    log_event("evidence.added", title=record["title"], url=record["url"], provider=record["provider"])
    return record


def evidence_markdown(records: list[dict[str, str]] | None = None) -> str:
    records = _load_records() if records is None else records
    lines = ["# Search Evidence", ""]
    if not records:
        lines.append("No evidence captured yet.")
        return "\n".join(lines)
    for index, record in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {record.get('title', '').strip() or 'Untitled'}",
                "",
                f"- query: {record.get('query', '')}",
                f"- provider: {record.get('provider', '')}",
                f"- url: {record.get('url', '')}",
                f"- retrieved_at: {record.get('retrieved_at', '')}",
                f"- confidence: {record.get('confidence', '')}",
                f"- recommended_use: {record.get('recommended_use', '')}",
                "",
                record.get("excerpt", ""),
                "",
                "Why it matters:",
                "",
                record.get("why_it_matters", ""),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def evidence_summary(max_records: int = 8) -> str:
    records = _load_records()
    if not records:
        return "No structured search evidence has been captured."
    lines = []
    for record in records[:max_records]:
        lines.append(
            f"- {record.get('title', 'Untitled')} ({record.get('url', '')}): "
            f"{record.get('recommended_use', '')}"
        )
    if len(records) > max_records:
        lines.append(f"- ... {len(records) - max_records} more evidence records")
    return "\n".join(lines)


def evidence_status(min_records: int = 1) -> tuple[bool, list[str]]:
    records = _load_records()
    issues: list[str] = []
    if len(records) < min_records:
        issues.append(f"at least {min_records} structured evidence record(s) required")
    for index, record in enumerate(records, start=1):
        missing = [field for field in REQUIRED_FIELDS if not str(record.get(field, "") or "").strip()]
        if missing:
            issues.append(f"evidence #{index} missing: {', '.join(missing)}")
        url = str(record.get("url", "") or "")
        if url and urlparse(url).scheme not in {"http", "https", "file"}:
            issues.append(f"evidence #{index} has invalid url: {url}")
    return not issues, issues


def decision_references_evidence() -> bool:
    text = read_text("docs/03-decision-record.md", "")
    if not text.strip():
        return False
    urls = [re.escape(str(record.get("url", "") or "")) for record in _load_records() if record.get("url")]
    if urls and any(re.search(url, text) for url in urls):
        return True
    evidence_section = text.split("## Evidence Used", 1)
    if len(evidence_section) != 2:
        return False
    tail = evidence_section[1].split("\n## ", 1)[0].strip()
    return bool(tail)
