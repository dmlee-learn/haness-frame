from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request

from .audit import log_event
from .client import RoleInvocationError, invoke
from .scorecard import mark_check
from .services import (
    debate_judge_independence,
    load_services,
    review_independence,
    service_configuration_issues,
    service_execution_identity,
)
from .storage import load_state

MAX_PROBE_BODY_BYTES = 1024 * 1024
LIVE_CHECK_PROMPT = "Reply with a short confirmation that this role is available."


def _state_snapshot() -> tuple[dict[str, object], list[str]]:
    try:
        return load_state(), []
    except ValueError as exc:
        return {}, [str(exc)]


def _expected_roles(services: dict[str, object], state: dict[str, object]) -> list[str]:
    expected: set[str] = set()
    for assignments in (services.get("role_service_assignments", {}), state.get("role_assignments", {})):
        if isinstance(assignments, dict):
            expected.update(str(role).strip() for role in assignments if str(role).strip())
    default_roles = state.get("default_roles", [])
    if isinstance(default_roles, list):
        expected.update(str(role).strip() for role in default_roles if isinstance(role, str) and role.strip())
    return sorted(expected)


def _assignment_issues(
    services: dict[str, object], state: dict[str, object], role_services: dict[str, object]
) -> list[str]:
    issues: list[str] = []
    service_assignments = services.get("role_service_assignments", {})
    if service_assignments is not None and not isinstance(service_assignments, dict):
        return ["services role_service_assignments must be a JSON object"]
    if not isinstance(service_assignments, dict):
        service_assignments = {}
    state_assignments = state.get("role_assignments", {})
    if not isinstance(state_assignments, dict):
        state_assignments = {}
    for role, assigned in service_assignments.items():
        role_name = str(role).strip()
        assigned_name = str(assigned).strip() if isinstance(assigned, str) else ""
        if not role_name or not assigned_name:
            issues.append(f"service assignment for role {role_name or '(empty)'} must name a service")
            continue
        configured = role_services.get(role_name, {})
        configured_name = str(configured.get("name", "") or "").strip() if isinstance(configured, dict) else ""
        if configured and not configured_name:
            issues.append(f"configured service for role {role_name} must include its assigned name")
        elif configured_name and configured_name != assigned_name:
            issues.append(f"service assignment mismatch for role {role_name}")
        state_name = state_assignments.get(role_name)
        if isinstance(state_name, str) and state_name.strip() and state_name.strip() != assigned_name:
            issues.append(f"state and service assignment snapshots disagree for role {role_name}")
    return issues


def _identity(service: dict[str, object]) -> tuple[object, ...]:
    provider, base_url, model = service_execution_identity(service)
    api_key_env = str(service.get("api_key_env", "") or "").strip()
    return provider, base_url, model, api_key_env, tuple(service_configuration_issues(service))


def _headers(service: dict[str, object]) -> dict[str, str]:
    env_name = str(service.get("api_key_env", "") or "").strip()
    if not env_name:
        return {}
    value = os.getenv(env_name, "").strip()
    return {"Authorization": f"Bearer {value}"} if value else {}


def _probe_url(service: dict[str, object]) -> str:
    base_url = str(service.get("base_url", "") or "").rstrip("/")
    provider = str(service.get("provider_type", "") or "").strip()
    if provider == "ollama":
        return f"{base_url}/api/tags"
    return f"{base_url}/models"


def _listed_models(provider: str, body: bytes) -> set[str] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    key = "models" if provider == "ollama" else "data"
    values = payload.get(key)
    if not isinstance(values, list):
        return None
    models: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        fields = ("name", "model") if provider == "ollama" else ("id",)
        for field in fields:
            model = str(value.get(field, "") or "").strip()
            if model:
                models.add(model)
                break
    return models


def _model_is_listed(provider: str, requested: str, available: set[str]) -> bool:
    if requested in available:
        return True
    return provider == "ollama" and ":" not in requested and f"{requested}:latest" in available


def _probe(service: dict[str, object], timeout: float) -> tuple[bool, str]:
    url = _probe_url(service)
    provider = str(service.get("provider_type", "") or "").strip()
    requested_model = str(service.get("model", "") or "").strip()
    request = urllib.request.Request(url, headers=_headers(service), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            detail = f"HTTP {status} {url}"
            if not 200 <= status < 400:
                return False, detail
            read = getattr(response, "read", None)
            if not callable(read):
                return True, detail
            body = read(MAX_PROBE_BODY_BYTES + 1)
            if len(body) > MAX_PROBE_BODY_BYTES:
                return True, f"{detail}; model list exceeds inspection limit"
            available = _listed_models(provider, body)
            if available is None:
                return True, f"{detail}; model list format not recognized"
            if not _model_is_listed(provider, requested_model, available):
                return False, f"{detail}; configured model is not listed: {requested_model}"
            return True, f"{detail}; configured model is available"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"{url}: {exc}"


def check_services(*, probe: bool = True, timeout: float = 2.0) -> dict[str, object]:
    try:
        payload = load_services()
    except ValueError as exc:
        report = {
            "valid": False,
            "probe_requested": probe,
            "service_count": 0,
            "role_count": 0,
            "expected_roles": [],
            "unassigned_roles": [],
            "services": [],
            "configuration_issues": [str(exc)],
            "warnings": [],
        }
        mark_check("services", False, "1 configuration issue(s)")
        log_event("services.checked", valid=False, probe=probe, services=0, configuration_issues=1)
        return report
    configuration_issues: list[str] = []
    state, state_issues = _state_snapshot()
    configuration_issues.extend(state_issues)
    expected_roles = _expected_roles(payload, state)
    role_services = payload.get("role_services")
    if not isinstance(role_services, dict):
        configuration_issues.append("services role_services must be a JSON object")
        role_services = {}
    elif not role_services:
        configuration_issues.append("services role_services must assign at least one role")
    configuration_issues.extend(_assignment_issues(payload, state, role_services))
    grouped: dict[tuple[object, ...], dict[str, object]] = {}
    unassigned: list[str] = [role for role in expected_roles if role not in role_services]
    for role, value in role_services.items():
        if not isinstance(value, dict) or not value:
            unassigned.append(str(role))
            continue
        key = _identity(value)
        entry = grouped.setdefault(key, {"service": value, "roles": []})
        entry["roles"].append(str(role))
    fallback = payload.get("fallback_service", {})
    if isinstance(fallback, dict) and fallback:
        key = _identity(fallback)
        entry = grouped.setdefault(key, {"service": fallback, "roles": []})
        entry["roles"].append("(fallback)")
    elif fallback is not None and not isinstance(fallback, dict):
        configuration_issues.append("services fallback_service must be a JSON object")

    results = []
    for entry in grouped.values():
        service = entry["service"]
        roles = sorted(entry["roles"])
        issues = service_configuration_issues(service)
        provider = str(service.get("provider_type", "") or "").strip()
        base_url = str(service.get("base_url", "") or "").strip()
        model = str(service.get("model", "") or "").strip()
        probe_ok: bool | None = None
        probe_detail = "not requested"
        if probe and not issues:
            probe_ok, probe_detail = _probe(service, max(0.1, min(timeout, 30.0)))
            if not probe_ok:
                issues.append(f"endpoint probe failed: {probe_detail}")
        results.append(
            {
                "name": str(service.get("name", "") or ""),
                "provider_type": provider,
                "base_url": base_url,
                "model": model,
                "roles": roles,
                "valid": not issues,
                "issues": issues,
                "probe_ok": probe_ok,
                "probe_detail": probe_detail,
            }
        )
    valid = bool(results) and not configuration_issues and not unassigned and all(item["valid"] for item in results)
    independence = review_independence()
    judge_independence = debate_judge_independence()
    warnings = []
    if independence.get("assessed") and not independence.get("independent_service"):
        warnings.append("coder and reviewer share the same provider endpoint and model")
    if judge_independence.get("assessed") and not judge_independence.get("independent_service"):
        shared_roles = ", ".join(str(role) for role in judge_independence.get("shared_roles", []))
        warnings.append(f"decision-maker judge shares provider endpoint and model with debate role(s): {shared_roles}")
    report = {
        "valid": valid,
        "probe_requested": probe,
        "service_count": len(results),
        "role_count": len(role_services),
        "expected_roles": expected_roles,
        "unassigned_roles": sorted(set(unassigned)),
        "services": results,
        "configuration_issues": configuration_issues,
        "review_independence": independence,
        "debate_judge_independence": judge_independence,
        "warnings": warnings,
    }
    issue_count = sum(len(item["issues"]) for item in results) + len(unassigned) + len(configuration_issues)
    detail = "ok" if valid else f"{issue_count} issue(s)"
    mark_check("services", valid, detail)
    log_event(
        "services.checked",
        valid=valid,
        probe=probe,
        services=len(results),
        configuration_issues=len(configuration_issues),
        independent_reviewer=independence.get("independent_service"),
        independent_debate_judge=judge_independence.get("independent_service"),
    )
    return report


def print_service_check(*, probe: bool = True, timeout: float = 2.0) -> int:
    report = check_services(probe=probe, timeout=timeout)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def live_check(
    *, role: str = "planner", timeout: float = 2.0, max_tokens: int = 32, retries: int = 0
) -> dict[str, object]:
    """Probe configured services and perform one content-redacted role call."""
    role = role.strip()
    if not role:
        raise ValueError("live-check role must not be empty")
    service_report = check_services(probe=True, timeout=timeout)
    invocation: dict[str, object] = {
        "attempted": False,
        "succeeded": False,
        "content_length": 0,
        "content_sha256": "",
    }
    if not service_report.get("valid"):
        invocation["failure_reason"] = "service configuration or endpoint probe failed"
        report = {
            "valid": False,
            "role": role,
            "service_check": service_report,
            "invocation": invocation,
        }
        log_event("services.live_check.completed", valid=False, role=role, invocation_attempted=False)
        return report

    invocation["attempted"] = True
    try:
        result = invoke(
            role,
            LIVE_CHECK_PROMPT,
            system="This is a provider availability check. Do not perform project work.",
            temperature=0.0,
            max_tokens=max(1, min(int(max_tokens), 256)),
            retries=max(0, min(int(retries), 3)),
        )
        content = str(result.get("content", ""))
        invocation_diagnostics = result.get("diagnostics", {})
        invocation.update(
            {
                "succeeded": bool(content),
                "provider_type": str(result.get("provider_type", "")),
                "service": invocation_diagnostics.get("selected_service", {})
                if isinstance(invocation_diagnostics, dict)
                else {},
                "used_fallback": bool(invocation_diagnostics.get("used_fallback", False))
                if isinstance(invocation_diagnostics, dict)
                else False,
                "attempt_count": len(invocation_diagnostics.get("attempts", []))
                if isinstance(invocation_diagnostics, dict)
                else 0,
                "content_length": len(content),
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            }
        )
        if not content:
            invocation["failure_reason"] = "provider returned empty content"
    except RoleInvocationError as exc:
        invocation.update(
            {
                "failure_reason": str(exc)[:500],
                "diagnostics": exc.diagnostics,
            }
        )
    except (RuntimeError, ValueError) as exc:
        invocation.update(
            {
                "failure_reason": str(exc)[:500],
                "diagnostics": {"error_type": type(exc).__name__},
            }
        )
    valid = bool(invocation["succeeded"])
    report = {
        "valid": valid,
        "role": role,
        "service_check": service_report,
        "invocation": invocation,
    }
    log_event(
        "services.live_check.completed",
        valid=valid,
        role=role,
        invocation_attempted=True,
        content_length=invocation["content_length"],
        content_sha256=invocation["content_sha256"],
    )
    return report


def print_live_check(
    *, role: str = "planner", timeout: float = 2.0, max_tokens: int = 32, retries: int = 0
) -> int:
    report = live_check(role=role, timeout=timeout, max_tokens=max_tokens, retries=retries)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1
