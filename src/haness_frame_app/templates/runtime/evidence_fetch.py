from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from .audit import log_event
from .evidence import add_evidence, load_evidence, update_evidence_source
from .evidence_policy import load_evidence_policy
from .network_safety import SafeRedirectHandler, validate_http_target
from .scorecard import mark_check
from .storage import write_text


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.ignored = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.ignored:
            self.ignored -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.ignored:
            return
        if self.in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


def _bounded_int(policy: dict[str, object], name: str, default: int, low: int, high: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"evidence policy {name} must be an integer")
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evidence policy {name} must be an integer") from exc


def _validate_target(url: str, policy: dict[str, object]) -> str:
    domains_value = policy.get("fetch_allowed_domains", [])
    if not isinstance(domains_value, list) or not all(isinstance(item, str) for item in domains_value):
        raise ValueError("evidence policy fetch_allowed_domains must be a string list")
    return validate_http_target(
        url,
        allow_private_network=bool(policy.get("allow_private_network", False)),
        allowed_domains=domains_value,
        label="evidence fetch",
    )


def _open_url(url: str, timeout: float, policy: dict[str, object]):  # type: ignore[no-untyped-def]
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "haness-frame-evidence/1.0", "Accept": "text/html,text/plain,application/json"},
        method="GET",
    )
    validator = lambda target: _validate_target(target, policy)
    return urllib.request.build_opener(SafeRedirectHandler(validator)).open(request, timeout=timeout)


def _extract_text(payload: bytes, content_type: str, charset: str | None) -> tuple[str, str]:
    text = payload.decode(charset or "utf-8", errors="replace")
    if content_type == "text/html":
        parser = _TextExtractor()
        parser.feed(text)
        title = " ".join(parser.title_parts)
        body = " ".join(parser.parts)
    else:
        title = ""
        body = text
    return re.sub(r"\s+", " ", title).strip(), re.sub(r"\s+", " ", body).strip()


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _fetch_source(url: str, policy: dict[str, object]) -> dict[str, object]:
    target = _validate_target(url, policy)
    timeout = float(_bounded_int(policy, "fetch_timeout_seconds", 10, 1, 60))
    max_bytes = _bounded_int(policy, "fetch_max_bytes", 1_000_000, 1024, 10_000_000)
    allowed_value = policy.get("fetch_allowed_content_types", ["text/html", "text/plain", "application/json"])
    if not isinstance(allowed_value, list) or not all(isinstance(item, str) for item in allowed_value):
        raise ValueError("evidence policy fetch_allowed_content_types must be a string list")
    allowed = {item.strip().lower() for item in allowed_value}
    try:
        with _open_url(target, timeout, policy) as response:
            final_url = str(response.geturl())
            _validate_target(final_url, policy)
            content_type = str(response.headers.get_content_type()).lower()
            if content_type not in allowed:
                raise ValueError(f"evidence fetch content type is not allowed: {content_type}")
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError(f"evidence fetch response exceeds {max_bytes} bytes")
            title, body = _extract_text(payload, content_type, response.headers.get_content_charset())
    except urllib.error.HTTPError as exc:
        raise ValueError(f"evidence fetch failed with HTTP {exc.code}: {target}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"evidence fetch failed: {target}: {exc}") from exc
    if not body:
        raise ValueError("evidence fetch response contains no usable text")
    return {
        "requested_url": target,
        "final_url": final_url,
        "title": title,
        "body": body,
        "content_type": content_type,
        "bytes": len(payload),
        "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def fetch_evidence(
    *,
    url: str,
    query: str,
    why_it_matters: str,
    recommended_use: str,
    confidence: str = "medium",
) -> dict[str, object]:
    policy = load_evidence_policy()
    if not bool(policy.get("fetch_enabled", True)):
        raise ValueError("evidence fetching is disabled by workspace/evidence-policy.json")
    excerpt_chars = _bounded_int(policy, "fetch_excerpt_chars", 1200, 100, 10000)
    source = _fetch_source(url, policy)
    final_url = str(source["final_url"])
    body = str(source["body"])
    record = add_evidence(
        query=query,
        provider="direct_url",
        url=final_url,
        title=str(source["title"]) or urlsplit(final_url).hostname or "Fetched evidence",
        excerpt=body[:excerpt_chars],
        confidence=confidence,
        why_it_matters=why_it_matters,
        recommended_use=recommended_use,
        source_sha256=str(source["source_sha256"]),
        source_bytes=int(source["bytes"]),
        source_content_type=str(source["content_type"]),
    )
    mark_check("evidence_fetch", True, final_url)
    log_event("evidence.fetched", url=final_url, content_type=source["content_type"], bytes=source["bytes"])
    return {"record": record, "content_type": source["content_type"], "bytes": source["bytes"]}


def verify_evidence_source(url: str) -> dict[str, object]:
    policy = load_evidence_policy()
    if not bool(policy.get("fetch_enabled", True)):
        raise ValueError("evidence fetching is disabled by workspace/evidence-policy.json")
    normalized = _normalized_url(url)
    record = next(
        (item for item in load_evidence() if _normalized_url(str(item.get("url", ""))) == normalized),
        None,
    )
    if record is None:
        raise ValueError(f"evidence source is not recorded: {url}")
    expected = str(record.get("source_sha256", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("evidence source has no valid fingerprint; capture it with evidence-fetch")
    source = _fetch_source(str(record["url"]), policy)
    actual = str(source["source_sha256"])
    same_url = _normalized_url(str(source["final_url"])) == normalized
    unchanged = expected == actual and same_url
    report = {
        "url": record["url"],
        "final_url": source["final_url"],
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "valid": unchanged,
        "status": "unchanged" if unchanged else ("redirect_changed" if not same_url else "content_changed"),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "content_type": source["content_type"],
        "bytes": source["bytes"],
    }
    _save_source_verification(report)
    log_event("evidence.source.verified", url=record["url"], valid=unchanged, status=report["status"])
    return report


def _save_source_verification(report: dict[str, object]) -> None:
    normalized = _normalized_url(str(report["url"]))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    write_text(f"workspace/evidence/source-verifications/{stamp}-{digest}.json", payload)
    write_text(f"workspace/evidence/source-verifications/latest-{digest}.json", payload)
    write_text("workspace/evidence/source-verifications/latest.json", payload)


def refresh_evidence_source(url: str) -> dict[str, object]:
    policy = load_evidence_policy()
    if not bool(policy.get("fetch_enabled", True)):
        raise ValueError("evidence fetching is disabled by workspace/evidence-policy.json")
    normalized = _normalized_url(url)
    record = next(
        (item for item in load_evidence() if _normalized_url(str(item.get("url", ""))) == normalized),
        None,
    )
    if record is None:
        raise ValueError(f"evidence source is not recorded: {url}")
    source = _fetch_source(str(record["url"]), policy)
    excerpt_chars = _bounded_int(policy, "fetch_excerpt_chars", 1200, 100, 10000)
    final_url = str(source["final_url"])
    updated = update_evidence_source(
        str(record["url"]),
        {
            "url": final_url,
            "title": str(source["title"]) or urlsplit(final_url).hostname or "Fetched evidence",
            "excerpt": str(source["body"])[:excerpt_chars],
            "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source_sha256": source["source_sha256"],
            "source_bytes": source["bytes"],
            "source_content_type": source["content_type"],
        },
    )
    report = {
        "url": updated["url"],
        "final_url": updated["url"],
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "valid": True,
        "status": "refreshed",
        "expected_sha256": updated["source_sha256"],
        "actual_sha256": updated["source_sha256"],
        "content_type": source["content_type"],
        "bytes": source["bytes"],
    }
    _save_source_verification(report)
    mark_check("evidence_fetch", True, final_url)
    log_event("evidence.source.refreshed", url=final_url, bytes=source["bytes"])
    return {"record": updated, "verification": report}


def verify_all_evidence_sources(limit: int | None = None) -> dict[str, object]:
    policy = load_evidence_policy()
    configured_limit = _bounded_int(policy, "max_source_checks_per_run", 20, 1, 100)
    if limit is not None:
        if isinstance(limit, bool) or limit < 1 or limit > configured_limit:
            raise ValueError(f"source check limit must be between 1 and {configured_limit}")
        checks_limit = limit
    else:
        checks_limit = configured_limit
    candidates = [
        item
        for item in load_evidence()
        if re.fullmatch(r"[0-9a-f]{64}", str(item.get("source_sha256", "")).strip().lower())
        and urlsplit(str(item.get("url", ""))).scheme in {"http", "https"}
    ]
    results: list[dict[str, object]] = []
    for record in candidates[:checks_limit]:
        url = str(record["url"])
        try:
            results.append(verify_evidence_source(url))
        except ValueError as exc:
            results.append({"url": url, "valid": False, "status": "check_error", "error": str(exc)[:500]})
    valid = all(bool(item.get("valid")) for item in results) and len(candidates) <= checks_limit
    report = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "valid": valid,
        "candidates": len(candidates),
        "checked": len(results),
        "unchanged": sum(item.get("status") == "unchanged" for item in results),
        "changed_or_failed": sum(not bool(item.get("valid")) for item in results),
        "skipped_by_limit": max(0, len(candidates) - checks_limit),
        "results": results,
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    write_text(f"workspace/evidence/source-verifications/batches/{stamp}.json", payload)
    write_text("workspace/evidence/source-verifications/latest-batch.json", payload)
    log_event(
        "evidence.sources.verified",
        valid=valid,
        checked=len(results),
        changed_or_failed=report["changed_or_failed"],
        skipped_by_limit=report["skipped_by_limit"],
    )
    return report
