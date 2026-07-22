from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .audit import log_event
from .claims import claim_policy_report
from .evidence_policy import evaluate_evidence_policy
from .scorecard import mark_check
from .storage import MUTATION_LOCK_TIMEOUT_SECONDS, ROOT, ensure_workspace, operation_lock, read_text, write_text

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
OPTIONAL_FIELDS = ["source_sha256", "source_bytes", "source_content_type"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _load_records() -> list[dict[str, str]]:
    ensure_workspace()
    payload = read_text(EVIDENCE_JSON, "[]")
    try:
        records = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{EVIDENCE_JSON} contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(records, list):
        raise ValueError(f"{EVIDENCE_JSON} root must be a JSON list")
    invalid = [index for index, item in enumerate(records, start=1) if not isinstance(item, dict)]
    if invalid:
        raise ValueError(f"{EVIDENCE_JSON} contains non-object record(s): {invalid}")
    return records


def load_evidence() -> list[dict[str, str]]:
    return _load_records()


def update_evidence_source(url: str, updates: dict[str, object]) -> dict[str, str]:
    allowed = {"url", "title", "excerpt", "retrieved_at", *OPTIONAL_FIELDS}
    unknown = sorted(set(updates) - allowed)
    if unknown:
        raise ValueError(f"unsupported evidence source update field(s): {', '.join(unknown)}")
    with operation_lock("evidence", "records", timeout=MUTATION_LOCK_TIMEOUT_SECONDS):
        records = _load_records()
        matches = [index for index, item in enumerate(records) if str(item.get("url", "")).strip() == url.strip()]
        if len(matches) != 1:
            raise ValueError(f"evidence source must match exactly one record: {url}")
        index = matches[0]
        updated = dict(records[index])
        updated.update({name: str(value or "").strip() for name, value in updates.items()})
        new_url = str(updated.get("url", "")).strip()
        if any(
            position != index and str(item.get("url", "")).strip() == new_url
            for position, item in enumerate(records)
        ):
            raise ValueError(f"duplicate evidence url: {new_url}")
        missing = [field for field in REQUIRED_FIELDS if not str(updated.get(field, "")).strip()]
        if missing:
            raise ValueError(f"updated evidence is missing fields: {', '.join(missing)}")
        records[index] = updated
        save_evidence(records)
        log_event("evidence.source.updated", url=new_url, fields=sorted(updates))
        return updated


def _load_search_plan() -> dict[str, object]:
    payload = read_text(SEARCH_PLAN_JSON, "{}")
    try:
        plan = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{SEARCH_PLAN_JSON} contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(plan, dict):
        raise ValueError(f"{SEARCH_PLAN_JSON} root must be a JSON object")
    return plan


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


def evidence_gap_counts() -> dict[str, int]:
    plan = _load_search_plan()
    searches = plan.get("searches", [])
    records = _load_records()
    if not isinstance(searches, list) or not searches:
        return {"planned": 0, "covered": 0, "missing": 0}
    known_queries = {str(item.get("query", "") or "").strip() for item in records}
    known_urls = {str(item.get("url", "") or "").strip() for item in records}
    covered = 0
    for item in searches:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        url = str(item.get("url", "")).strip()
        if query in known_queries or url in known_urls:
            covered += 1
    return {"planned": len(searches), "covered": covered, "missing": max(0, len(searches) - covered)}


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
    with operation_lock("evidence", "records", timeout=MUTATION_LOCK_TIMEOUT_SECONDS):
        return _commit_evidence_draft_unlocked(path)


def _commit_evidence_draft_unlocked(path: str) -> dict[str, object]:
    draft_path = Path(path)
    draft_path = (draft_path if draft_path.is_absolute() else ROOT / draft_path).resolve(strict=False)
    try:
        draft_path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("evidence draft must be inside the project") from exc
    if not draft_path.is_file():
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
        item = {field: str(record.get(field, "") or "").strip() for field in REQUIRED_FIELDS}
        item.update(
            {
                field: str(record.get(field, "") or "").strip()
                for field in OPTIONAL_FIELDS
                if str(record.get(field, "") or "").strip()
            }
        )
        cleaned.append(item)
    write_text(EVIDENCE_JSON, json.dumps(cleaned, indent=2, ensure_ascii=False))
    try:
        write_text(EVIDENCE_MD, evidence_markdown(cleaned))
    except OSError as exc:
        log_event("evidence.markdown.rebuild_failed", record_count=len(cleaned), error=type(exc).__name__)
        raise RuntimeError(
            "structured evidence was saved but its Markdown view could not be rebuilt; "
            "run `python app.py evidence-rebuild`"
        ) from exc


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
    source_sha256: str = "",
    source_bytes: int | str = "",
    source_content_type: str = "",
) -> dict[str, str]:
    with operation_lock("evidence", "records", timeout=MUTATION_LOCK_TIMEOUT_SECONDS):
        return _add_evidence_unlocked(
            query,
            provider,
            url,
            title,
            excerpt,
            confidence,
            why_it_matters,
            recommended_use,
            retrieved_at,
            source_sha256,
            source_bytes,
            source_content_type,
        )


def _add_evidence_unlocked(
    query: str,
    provider: str,
    url: str,
    title: str,
    excerpt: str,
    confidence: str,
    why_it_matters: str,
    recommended_use: str,
    retrieved_at: str,
    source_sha256: str = "",
    source_bytes: int | str = "",
    source_content_type: str = "",
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
    optional = {
        "source_sha256": str(source_sha256 or "").strip().lower(),
        "source_bytes": str(source_bytes or "").strip(),
        "source_content_type": source_content_type.strip().lower(),
    }
    record.update({name: value for name, value in optional.items() if value})
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
                *(
                    [f"- source_sha256: {record.get('source_sha256', '')}"]
                    if record.get("source_sha256")
                    else []
                ),
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


def evidence_derivative_report(records: list[dict[str, str]] | None = None) -> dict[str, object]:
    source_records = _load_records() if records is None else records
    path = ROOT / EVIDENCE_MD
    if not path.exists():
        return {"valid": True, "status": "missing", "issues": [], "path": EVIDENCE_MD}
    expected = evidence_markdown(source_records)
    matches = path.read_text(encoding="utf-8", errors="replace") == expected
    issues = [] if matches else [f"{EVIDENCE_MD} is stale; run `python app.py evidence-rebuild`"]
    return {
        "valid": matches,
        "status": "current" if matches else "stale",
        "issues": issues,
        "path": EVIDENCE_MD,
    }


def rebuild_evidence_markdown() -> dict[str, object]:
    with operation_lock("evidence", "records", timeout=MUTATION_LOCK_TIMEOUT_SECONDS):
        records = _load_records()
        path = write_text(EVIDENCE_MD, evidence_markdown(records))
        log_event("evidence.markdown.rebuilt", record_count=len(records))
        return {"path": str(path), "record_count": len(records), "status": "rebuilt"}


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


def evidence_policy_report() -> dict[str, object]:
    try:
        records = _load_records()
        derivative = evidence_derivative_report(records)
        gaps = evidence_gap_counts()
        report = evaluate_evidence_policy(
            records,
            planned_searches=gaps["planned"],
            covered_searches=gaps["covered"],
        )
        claims = claim_policy_report()
    except ValueError as exc:
        return {
            "valid": False,
            "issues": [str(exc)],
            "claims": {"valid": False, "issues": []},
            "derivative": {"valid": False, "status": "unavailable", "issues": []},
        }
    report["claims"] = claims
    report["derivative"] = derivative
    report["issues"] = [*report["issues"], *claims["issues"], *derivative["issues"]]
    report["valid"] = bool(report["valid"] and claims["valid"] and derivative["valid"])
    return report


def evidence_status(min_records: int | None = None) -> tuple[bool, list[str]]:
    try:
        records = _load_records()
    except ValueError as exc:
        return False, [str(exc)]
    issues: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = [field for field in REQUIRED_FIELDS if not str(record.get(field, "") or "").strip()]
        if missing:
            issues.append(f"evidence #{index} missing: {', '.join(missing)}")
        url = str(record.get("url", "") or "")
        if url and urlparse(url).scheme not in {"http", "https", "file"}:
            issues.append(f"evidence #{index} has invalid url: {url}")
    try:
        gaps = evidence_gap_counts()
        policy_result = evaluate_evidence_policy(
            records,
            planned_searches=gaps["planned"],
            covered_searches=gaps["covered"],
            min_records_override=min_records,
        )
        claims = claim_policy_report()
        derivative = evidence_derivative_report(records)
    except ValueError as exc:
        return False, [*issues, str(exc)]
    issues.extend(str(item) for item in policy_result["issues"])
    issues.extend(str(item) for item in claims["issues"])
    issues.extend(str(item) for item in derivative["issues"])
    return not issues, issues


def decision_references_evidence() -> bool:
    text = read_text("docs/03-decision-record.md", "")
    if not text.strip():
        return False
    try:
        records = _load_records()
    except ValueError:
        return False
    urls = [re.escape(str(record.get("url", "") or "")) for record in records if record.get("url")]
    if urls and any(re.search(url, text) for url in urls):
        return True
    evidence_section = text.split("## Evidence Used", 1)
    if len(evidence_section) != 2:
        return False
    tail = evidence_section[1].split("\n## ", 1)[0].strip()
    return bool(tail)
