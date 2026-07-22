from __future__ import annotations

import json
import os
import urllib.parse

from .storage import read_text


_OPENAI_COMPATIBLE_PROVIDERS = {"openai", "openai_compatible", "vllm", "codex"}
SUPPORTED_PROVIDERS = _OPENAI_COMPATIBLE_PROVIDERS | {"ollama"}
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120
MAX_REQUEST_TIMEOUT_SECONDS = 600


def load_services() -> dict[str, object]:
    raw = read_text("workspace/services.json", "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"workspace/services.json contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("workspace/services.json root must be a JSON object")
    return payload


def role_service(role: str) -> dict[str, object]:
    payload = load_services()
    role_services = payload.get("role_services", {})
    if not isinstance(role_services, dict):
        return {}
    service = role_services.get(role, {})
    return service if isinstance(service, dict) else {}


def fallback_service() -> dict[str, object]:
    payload = load_services()
    service = payload.get("fallback_service", {})
    return service if isinstance(service, dict) else {}


def service_configuration_issues(service: dict[str, object]) -> list[str]:
    issues: list[str] = []
    enabled = service.get("enabled", True)
    if not isinstance(enabled, bool):
        issues.append("enabled must be a boolean")
    elif not enabled:
        issues.append("service is disabled")
    provider = str(service.get("provider_type", "") or "").strip()
    if provider not in SUPPORTED_PROVIDERS:
        issues.append(f"unsupported provider_type: {provider or '(empty)'}")
    base_url = str(service.get("base_url", "") or "").strip()
    if not base_url:
        issues.append("base_url is required")
    else:
        try:
            parsed = urllib.parse.urlsplit(base_url)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                issues.append("base_url must use http:// or https:// with a hostname")
            if parsed.username or parsed.password:
                issues.append("base_url must not contain credentials")
            if parsed.query or parsed.fragment:
                issues.append("base_url must not contain a query or fragment")
            _ = parsed.port
        except ValueError:
            issues.append("base_url is malformed")
    if not str(service.get("model", "") or "").strip():
        issues.append("model is required")
    timeout = service.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        issues.append("request_timeout_seconds must be an integer")
    elif not 1 <= timeout <= MAX_REQUEST_TIMEOUT_SECONDS:
        issues.append(f"request_timeout_seconds must be between 1 and {MAX_REQUEST_TIMEOUT_SECONDS}")
    env_name = str(service.get("api_key_env", "") or "").strip()
    if env_name and not os.getenv(env_name, "").strip():
        issues.append(f"API key environment variable is empty: {env_name}")
    return issues


def service_request_timeout(service: dict[str, object]) -> int:
    value = service.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("request_timeout_seconds must be an integer")
    if not 1 <= value <= MAX_REQUEST_TIMEOUT_SECONDS:
        raise ValueError(f"request_timeout_seconds must be between 1 and {MAX_REQUEST_TIMEOUT_SECONDS}")
    return value


def _canonical_provider(provider: object) -> str:
    value = str(provider or "").strip().lower()
    return "openai_compatible" if value in _OPENAI_COMPATIBLE_PROVIDERS else value


def _canonical_base_url(base_url: object) -> str:
    value = str(base_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urllib.parse.urlsplit(value)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if not scheme or not host:
            return value.rstrip("/").lower()
        port = parsed.port
        if (scheme, port) in {("http", 80), ("https", 443)}:
            port = None
        rendered_host = f"[{host}]" if ":" in host else host
        netloc = f"{rendered_host}:{port}" if port else rendered_host
        path = parsed.path.rstrip("/")
        return urllib.parse.urlunsplit((scheme, netloc, path, "", ""))
    except ValueError:
        return value.rstrip("/").lower()


def service_execution_identity(service: dict[str, object]) -> tuple[str, str, str]:
    return (
        _canonical_provider(service.get("provider_type", "")),
        _canonical_base_url(service.get("base_url", "")),
        str(service.get("model", "") or "").strip(),
    )


def review_independence() -> dict[str, object]:
    try:
        payload = load_services()
    except ValueError as exc:
        return {"assessed": False, "independent_service": None, "reason": str(exc)}
    role_services = payload.get("role_services", {})
    if not isinstance(role_services, dict):
        role_services = {}
    coder = role_services.get("coder", {})
    reviewer = role_services.get("reviewer", {})
    if not isinstance(coder, dict) or not coder or not isinstance(reviewer, dict) or not reviewer:
        return {"assessed": False, "independent_service": None, "reason": "coder or reviewer is unassigned"}
    coder_identity = service_execution_identity(coder)
    reviewer_identity = service_execution_identity(reviewer)
    if not all(coder_identity) or not all(reviewer_identity):
        return {"assessed": False, "independent_service": None, "reason": "service identity is incomplete"}
    independent = coder_identity != reviewer_identity
    return {
        "assessed": True,
        "independent_service": independent,
        "reason": "distinct provider endpoint or model" if independent else "coder and reviewer share provider endpoint and model",
    }


def debate_judge_independence(participant_roles: list[str] | None = None) -> dict[str, object]:
    try:
        payload = load_services()
    except ValueError as exc:
        return {
            "assessed": False,
            "independent_service": None,
            "reason": str(exc),
            "shared_roles": [],
        }
    role_services = payload.get("role_services", {})
    if not isinstance(role_services, dict):
        role_services = {}
    judge = role_services.get("decision_maker", {})
    judge_identity = service_execution_identity(judge) if isinstance(judge, dict) else ("", "", "")
    default_roles = [
        "project_scout", "context_curator", "researcher", "planner",
        "designer", "architect", "critic",
    ]
    selected = participant_roles if participant_roles is not None else default_roles
    participant_identities: list[tuple[str, tuple[str, str, str]]] = []
    for role in selected:
        service = role_services.get(role, {})
        if isinstance(service, dict) and service:
            participant_identities.append((role, service_execution_identity(service)))
    if not all(judge_identity):
        return {"assessed": False, "independent_service": None, "reason": "decision-maker judge is unassigned or incomplete", "shared_roles": []}
    if not participant_identities or any(not all(identity) for _, identity in participant_identities):
        return {"assessed": False, "independent_service": None, "reason": "participant service identity is missing or incomplete", "shared_roles": []}
    shared = [role for role, identity in participant_identities if identity == judge_identity]
    return {
        "assessed": True,
        "independent_service": not shared,
        "reason": "judge has a distinct configured identity" if not shared else "judge shares configured participant identity",
        "shared_roles": shared,
    }
