from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .audit import log_event
from .network_safety import SafeRedirectHandler, validate_http_target
from .scorecard import mark_check
from .storage import read_text, write_text

POLICY_FILE = "workspace/search-policy.json"
SEARCH_PLAN_FILE = "workspace/evidence/search-plan.json"
DISCOVERY_ROOT = "workspace/evidence/discoveries"


def _bounded_int(policy: dict[str, object], name: str, default: int, low: int, high: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"search policy {name} must be an integer")
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"search policy {name} must be an integer") from exc


def load_search_policy() -> dict[str, object]:
    try:
        policy = json.loads(read_text(POLICY_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid search policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("search policy must be a JSON object")
    return policy


def _endpoint(policy: dict[str, object]) -> str:
    if str(policy.get("provider", "searxng")).strip().lower() != "searxng":
        raise ValueError("search policy provider must be searxng")
    base_url = str(policy.get("base_url", "") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("search policy base_url is required")
    endpoint = base_url if urlsplit(base_url).path.rstrip("/").endswith("/search") else f"{base_url}/search"
    domains_value = policy.get("allowed_domains", [])
    if not isinstance(domains_value, list) or not all(isinstance(item, str) for item in domains_value):
        raise ValueError("search policy allowed_domains must be a string list")
    return validate_http_target(
        endpoint,
        allow_private_network=bool(policy.get("allow_private_network", False)),
        allowed_domains=domains_value,
        label="search endpoint",
    )


def _open_search(url: str, timeout: int, validator):  # type: ignore[no-untyped-def]
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "haness-frame-search/1.0"},
        method="GET",
    )
    return urllib.request.build_opener(SafeRedirectHandler(validator)).open(request, timeout=timeout)


def _queries(query: str, max_queries: int) -> list[str]:
    if query.strip():
        return [query.strip()]
    try:
        plan = json.loads(read_text(SEARCH_PLAN_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid search plan JSON: {exc}") from exc
    searches = plan.get("searches", []) if isinstance(plan, dict) else []
    values = []
    for item in searches if isinstance(searches, list) else []:
        value = str(item.get("query", "") or "").strip() if isinstance(item, dict) else ""
        if value and value not in values:
            values.append(value)
    if not values:
        raise ValueError("no query supplied and the search plan is empty")
    return values[:max_queries]


def _candidate(item: object, query: str) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url", "") or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    normalized_url = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    engines = item.get("engines", [])
    if not isinstance(engines, list):
        engines = [str(item.get("engine", "") or "")]
    return {
        "query": query,
        "url": normalized_url,
        "title": re.sub(r"\s+", " ", str(item.get("title", "") or "")).strip(),
        "snippet": re.sub(r"\s+", " ", str(item.get("content", "") or "")).strip()[:1000],
        "engines": [str(value) for value in engines if str(value).strip()],
        "score": item.get("score"),
        "category": str(item.get("category", "") or ""),
        "approved_evidence": False,
    }


def discover_sources(query: str = "", *, limit: int | None = None) -> dict[str, object]:
    policy = load_search_policy()
    if not bool(policy.get("enabled", False)):
        raise ValueError("search discovery is disabled by workspace/search-policy.json")
    max_queries = _bounded_int(policy, "max_queries_per_run", 8, 1, 50)
    max_results = _bounded_int(policy, "max_results_per_query", 5, 1, 50)
    if limit is not None:
        max_results = max(1, min(limit, max_results))
    timeout = _bounded_int(policy, "timeout_seconds", 15, 1, 60)
    max_bytes = _bounded_int(policy, "max_response_bytes", 2_000_000, 1024, 10_000_000)
    endpoint = _endpoint(policy)
    domains = policy.get("allowed_domains", [])
    validator = lambda target: validate_http_target(
        target,
        allow_private_network=bool(policy.get("allow_private_network", False)),
        allowed_domains=domains,
        label="search endpoint",
    )
    candidates: list[dict[str, object]] = []
    searched = []
    for search_query in _queries(query, max_queries):
        params = {
            "q": search_query,
            "format": "json",
            "language": str(policy.get("language", "all") or "all"),
            "categories": str(policy.get("categories", "general") or "general"),
            "safesearch": str(_bounded_int(policy, "safesearch", 1, 0, 2)),
        }
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            with _open_search(url, timeout, validator) as response:
                payload = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise ValueError(f"search endpoint failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ValueError(f"search endpoint failed: {exc}") from exc
        if len(payload) > max_bytes:
            raise ValueError(f"search response exceeds {max_bytes} bytes")
        try:
            result = json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError("search endpoint returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise ValueError("SearXNG response requires a results list")
        added = 0
        for item in result["results"]:
            candidate = _candidate(item, search_query)
            if candidate is None or any(value["url"] == candidate["url"] for value in candidates):
                continue
            candidates.append(candidate)
            added += 1
            if added >= max_results:
                break
        searched.append({"query": search_query, "candidate_count": added})
    report = {
        "provider": "searxng",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "searched": searched,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "notice": "Candidates are not approved evidence. Fetch and validate a direct source before using it.",
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_text(f"{DISCOVERY_ROOT}/{stamp}.json", json.dumps(report, indent=2, ensure_ascii=False))
    write_text(f"{DISCOVERY_ROOT}/latest.json", json.dumps(report, indent=2, ensure_ascii=False))
    mark_check("search_discovery", True, f"{len(candidates)} candidate(s)")
    log_event("search.discovery.completed", queries=len(searched), candidates=len(candidates))
    return report
