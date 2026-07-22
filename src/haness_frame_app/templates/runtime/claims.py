from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit, urlunsplit

from .audit import log_event
from .evidence_policy import load_evidence_policy
from .scorecard import mark_check
from .storage import MUTATION_LOCK_TIMEOUT_SECONDS, operation_lock, read_text, write_text

CLAIMS_JSON = "workspace/evidence/claim-evidence.json"
EVIDENCE_JSON = "workspace/evidence/search-evidence.json"
DECISION_FILE = "docs/03-decision-record.md"
STATUSES = {"accepted", "uncertain", "rejected"}


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _json_list(path: str) -> tuple[list[dict[str, object]], list[str]]:
    try:
        payload = json.loads(read_text(path, "[]"))
    except json.JSONDecodeError as exc:
        return [], [f"invalid JSON in {path}: {exc}"]
    if not isinstance(payload, list):
        return [], [f"{path} must contain a JSON list"]
    invalid = [index for index, item in enumerate(payload, start=1) if not isinstance(item, dict)]
    if invalid:
        return [], [f"{path} contains non-object record(s): {invalid}"]
    return payload, []


def load_claims() -> list[dict[str, object]]:
    records, issues = _json_list(CLAIMS_JSON)
    if issues:
        raise ValueError(issues[0])
    return records


def _policy_bool(policy: dict[str, object], name: str, default: bool) -> bool:
    value = policy.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"evidence policy {name} must be a boolean")
    return value


def _policy_int(policy: dict[str, object], name: str, default: int, low: int, high: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"evidence policy {name} must be an integer")
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evidence policy {name} must be an integer") from exc


def _known_evidence_urls() -> tuple[set[str], list[str]]:
    records, issues = _json_list(EVIDENCE_JSON)
    urls = {
        _normalized_url(str(item.get("url", "") or ""))
        for item in records
        if str(item.get("url", "") or "").strip()
    }
    return urls, issues


def _string_list(record: dict[str, object], field: str, index: int, issues: list[str]) -> list[str]:
    value = record.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        issues.append(f"claim #{index} {field} must be a string list")
        return []
    return [item.strip() for item in value]


def claim_policy_report() -> dict[str, object]:
    policy = load_evidence_policy()
    required = _policy_bool(policy, "require_claim_matrix", False)
    min_claims = _policy_int(policy, "min_claims", 1, 1, 100)
    min_support = _policy_int(policy, "min_supporting_sources_per_claim", 1, 1, 20)
    require_resolution = _policy_bool(policy, "require_challenge_resolution", True)
    allowed = policy.get("allowed_claim_confidence", ["high", "medium"])
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) and item.strip() for item in allowed):
        raise ValueError("evidence policy allowed_claim_confidence must be a non-empty string list")
    allowed_confidence = {item.strip().lower() for item in allowed}
    claims, issues = _json_list(CLAIMS_JSON)
    known_urls, evidence_issues = _known_evidence_urls()
    issues.extend(evidence_issues)
    if required and len(claims) < min_claims:
        issues.append(f"at least {min_claims} structured claim(s) required")
    seen_ids: set[str] = set()
    accepted = 0
    for index, record in enumerate(claims, start=1):
        claim_id = str(record.get("claim_id", "") or "").strip()
        claim = str(record.get("claim", "") or "").strip()
        status = str(record.get("status", "") or "").strip().lower()
        confidence = str(record.get("confidence", "") or "").strip().lower()
        resolution = str(record.get("resolution", "") or "").strip()
        if not claim_id or not claim:
            issues.append(f"claim #{index} requires claim_id and claim")
        if claim_id in seen_ids:
            issues.append(f"duplicate claim_id: {claim_id}")
        seen_ids.add(claim_id)
        if status not in STATUSES:
            issues.append(f"claim #{index} status is invalid: {status or '(empty)'}")
        if confidence not in allowed_confidence:
            issues.append(f"claim #{index} confidence is not allowed: {confidence or '(empty)'}")
        supporting = _string_list(record, "supporting_urls", index, issues)
        challenging = _string_list(record, "challenging_urls", index, issues)
        normalized_support = {_normalized_url(url) for url in supporting}
        normalized_challenge = {_normalized_url(url) for url in challenging}
        unknown = sorted((normalized_support | normalized_challenge) - known_urls)
        if unknown:
            issues.append(f"claim #{index} references unknown evidence URL(s): {', '.join(unknown)}")
        if normalized_support & normalized_challenge:
            issues.append(f"claim #{index} uses the same URL as support and challenge")
        if status == "accepted":
            accepted += 1
            if len(normalized_support) < min_support:
                issues.append(f"claim #{index} requires at least {min_support} supporting source(s)")
        if challenging and require_resolution and len(resolution) < 20:
            issues.append(f"claim #{index} challenge resolution must be at least 20 characters")
    if required and accepted < 1:
        issues.append("at least one accepted claim is required")
    return {
        "valid": not issues,
        "required": required,
        "issues": issues,
        "claims": len(claims),
        "accepted_claims": accepted,
        "policy_file": "workspace/evidence-policy.json",
    }


def add_claim(
    *,
    claim: str,
    supporting_urls: list[str],
    challenging_urls: list[str] | None = None,
    status: str = "accepted",
    confidence: str = "medium",
    resolution: str = "",
) -> dict[str, object]:
    with operation_lock("claims", "records", timeout=MUTATION_LOCK_TIMEOUT_SECONDS):
        return _add_claim_unlocked(
            claim=claim,
            supporting_urls=supporting_urls,
            challenging_urls=challenging_urls,
            status=status,
            confidence=confidence,
            resolution=resolution,
        )


def _add_claim_unlocked(
    *,
    claim: str,
    supporting_urls: list[str],
    challenging_urls: list[str] | None,
    status: str,
    confidence: str,
    resolution: str,
) -> dict[str, object]:
    claim = claim.strip()
    if not claim:
        raise ValueError("claim must be a non-empty string")
    if len(claim) > 4000:
        raise ValueError("claim must not exceed 4000 characters")
    if not isinstance(supporting_urls, list) or not isinstance(challenging_urls or [], list):
        raise ValueError("claim evidence URLs must be lists")
    claim_id = f"claim-{hashlib.sha256(claim.casefold().encode('utf-8')).hexdigest()[:12]}"
    records = load_claims()
    if any(str(item.get("claim_id", "")) == claim_id for item in records):
        raise ValueError(f"duplicate claim: {claim_id}")
    record: dict[str, object] = {
        "claim_id": claim_id,
        "claim": claim,
        "status": status.strip().lower(),
        "confidence": confidence.strip().lower(),
        "supporting_urls": [item.strip() for item in supporting_urls if item.strip()],
        "challenging_urls": [item.strip() for item in (challenging_urls or []) if item.strip()],
        "resolution": resolution.strip(),
    }
    records.append(record)
    previous_payload = json.dumps(records[:-1], indent=2, ensure_ascii=False)
    write_text(CLAIMS_JSON, json.dumps(records, indent=2, ensure_ascii=False))
    try:
        report = claim_policy_report()
    except Exception:
        write_text(CLAIMS_JSON, previous_payload)
        raise
    if any(f"claim #{len(records)}" in issue for issue in report["issues"]):
        write_text(CLAIMS_JSON, previous_payload)
        raise ValueError("invalid claim: " + "; ".join(report["issues"]))
    mark_check("claim_evidence", bool(report["valid"]), f"{len(records)} claim(s)")
    log_event("claim.added", claim_id=claim_id, status=record["status"], support=len(record["supporting_urls"]))
    return record


def decision_claim_issues() -> list[str]:
    report = claim_policy_report()
    if not report["required"] or not report["valid"]:
        return []
    text = read_text(DECISION_FILE, "").casefold()
    issues = []
    for record in load_claims():
        if str(record.get("status", "")).lower() != "accepted":
            continue
        claim_id = str(record.get("claim_id", "")).casefold()
        claim = str(record.get("claim", "")).casefold()
        if claim_id not in text and claim not in text:
            issues.append(f"Decision Record must reference accepted claim: {record.get('claim_id', '')}")
    return issues


def claims_markdown() -> str:
    records = load_claims()
    if not records:
        return "# Claim Evidence\n\nNo structured claims captured yet.\n"
    lines = ["# Claim Evidence", ""]
    for record in records:
        supporting = record.get("supporting_urls", [])
        challenging = record.get("challenging_urls", [])
        supporting_text = ", ".join(str(item) for item in supporting) if isinstance(supporting, list) else "(invalid)"
        challenging_text = ", ".join(str(item) for item in challenging) if isinstance(challenging, list) else "(invalid)"
        lines.extend(
            [
                f"## {record.get('claim_id', '')}",
                "",
                str(record.get("claim", "")),
                "",
                f"- status: {record.get('status', '')}",
                f"- confidence: {record.get('confidence', '')}",
                f"- supporting_urls: {supporting_text}",
                f"- challenging_urls: {challenging_text}",
                f"- resolution: {record.get('resolution', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def claim_summary() -> str:
    records = load_claims()
    if not records:
        return "- No structured claims captured yet."
    return "\n".join(
        f"- {item.get('claim_id', '')}: {item.get('claim', '')} [{item.get('status', '')}]"
        for item in records
    )
