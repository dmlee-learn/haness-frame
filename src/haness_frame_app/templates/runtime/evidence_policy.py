from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from .storage import read_text

POLICY_FILE = "workspace/evidence-policy.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load_evidence_policy() -> dict[str, object]:
    try:
        policy = json.loads(read_text(POLICY_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evidence policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("evidence policy must be a JSON object")
    return policy


def _policy_int(policy: dict[str, object], name: str, default: int, minimum: int, maximum: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"evidence policy {name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evidence policy {name} must be an integer") from exc
    return max(minimum, min(parsed, maximum))


def _policy_float(policy: dict[str, object], name: str, default: float) -> float:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"evidence policy {name} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evidence policy {name} must be a number") from exc
    return max(0.0, min(parsed, 1.0))


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _retrieved_at(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _source_verification(record: dict[str, str]) -> dict[str, object] | None:
    normalized = _normalized_url(str(record.get("url", "")))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    text = read_text(f"workspace/evidence/source-verifications/latest-{digest}.json", "")
    if not text:
        return None
    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        return {"valid": False, "status": "invalid_report"}
    return report if isinstance(report, dict) else {"valid": False, "status": "invalid_report"}


def evaluate_evidence_policy(
    records: list[dict[str, str]],
    *,
    planned_searches: int = 0,
    covered_searches: int = 0,
    min_records_override: int | None = None,
) -> dict[str, object]:
    policy = load_evidence_policy()
    minimum = _policy_int(policy, "min_records", 2, 1, 100)
    if min_records_override is not None:
        minimum = max(1, min_records_override)
    min_urls = _policy_int(policy, "min_distinct_urls", 2, 1, 100)
    max_age_days = _policy_int(policy, "max_age_days", 3650, 1, 36500)
    future_skew = _policy_int(policy, "max_future_skew_minutes", 10, 0, 1440)
    min_excerpt_chars = _policy_int(policy, "min_excerpt_chars", 20, 1, 10000)
    min_coverage = _policy_float(policy, "min_search_coverage_ratio", 0.0)
    allowed = policy.get("allowed_confidence", ["high", "medium"])
    if not isinstance(allowed, list) or not all(isinstance(item, str) and item.strip() for item in allowed):
        raise ValueError("evidence policy allowed_confidence must be a non-empty string list")
    allowed_confidence = {item.strip().lower() for item in allowed}
    require_source_fingerprint = policy.get("require_source_fingerprint", False)
    if not isinstance(require_source_fingerprint, bool):
        raise ValueError("evidence policy require_source_fingerprint must be a boolean")
    require_source_revalidation = policy.get("require_source_revalidation", False)
    if not isinstance(require_source_revalidation, bool):
        raise ValueError("evidence policy require_source_revalidation must be a boolean")
    max_verification_age = _policy_int(policy, "max_source_verification_age_days", 30, 1, 3650)

    issues: list[str] = []
    if len(records) < minimum:
        issues.append(f"at least {minimum} structured evidence record(s) required")
    normalized_urls = [_normalized_url(str(item.get("url", ""))) for item in records if item.get("url")]
    if len(set(normalized_urls)) < min_urls:
        issues.append(f"at least {min_urls} distinct evidence URL(s) required")
    duplicates = sorted({url for url in normalized_urls if normalized_urls.count(url) > 1})
    if duplicates:
        issues.append(f"duplicate normalized evidence URL(s): {', '.join(duplicates)}")

    now = dt.datetime.now(dt.timezone.utc)
    for index, record in enumerate(records, start=1):
        confidence = str(record.get("confidence", "")).strip().lower()
        if confidence and confidence not in allowed_confidence:
            issues.append(f"evidence #{index} confidence is not allowed: {confidence}")
        excerpt = str(record.get("excerpt", "")).strip()
        if excerpt and len(excerpt) < min_excerpt_chars:
            issues.append(f"evidence #{index} excerpt is shorter than {min_excerpt_chars} characters")
        retrieved = str(record.get("retrieved_at", "")).strip()
        source_sha256 = str(record.get("source_sha256", "")).strip().lower()
        if source_sha256 and not _SHA256.fullmatch(source_sha256):
            issues.append(f"evidence #{index} source_sha256 is invalid")
        if require_source_fingerprint and str(record.get("provider", "")).strip() == "direct_url" and not source_sha256:
            issues.append(f"evidence #{index} direct_url source fingerprint is required")
        if source_sha256:
            verification = _source_verification(record)
            if verification is None:
                if require_source_revalidation:
                    issues.append(f"evidence #{index} source revalidation is required")
            else:
                expected = str(verification.get("expected_sha256", "")).strip().lower()
                if expected != source_sha256:
                    if require_source_revalidation:
                        issues.append(f"evidence #{index} source revalidation does not match its fingerprint")
                elif not verification.get("valid"):
                    issues.append(
                        f"evidence #{index} source changed: {verification.get('status', 'verification_failed')}"
                    )
                else:
                    checked_at = str(verification.get("checked_at", "")).strip()
                    try:
                        checked = _retrieved_at(checked_at)
                    except ValueError:
                        issues.append(f"evidence #{index} source verification timestamp is invalid")
                    else:
                        if require_source_revalidation and checked < now - dt.timedelta(days=max_verification_age):
                            issues.append(
                                f"evidence #{index} source verification is older than {max_verification_age} days"
                            )
        if retrieved:
            try:
                timestamp = _retrieved_at(retrieved)
            except ValueError:
                issues.append(f"evidence #{index} retrieved_at is not valid ISO-8601: {retrieved}")
                continue
            if timestamp > now + dt.timedelta(minutes=future_skew):
                issues.append(f"evidence #{index} retrieved_at is in the future: {retrieved}")
            if timestamp < now - dt.timedelta(days=max_age_days):
                issues.append(f"evidence #{index} is older than {max_age_days} days")

    coverage = covered_searches / planned_searches if planned_searches else 0.0
    if min_coverage > 0 and coverage < min_coverage:
        issues.append(f"search evidence coverage {coverage:.2f} is below required {min_coverage:.2f}")
    return {
        "valid": not issues,
        "issues": issues,
        "records": len(records),
        "distinct_urls": len(set(normalized_urls)),
        "search_coverage_ratio": coverage,
        "policy_file": POLICY_FILE,
    }
