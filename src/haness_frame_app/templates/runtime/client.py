from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .prompting import build_messages
from .services import (
    fallback_service,
    role_service,
    service_configuration_issues,
    service_execution_identity,
    service_request_timeout,
)
from .audit import log_event


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class ProviderResponseError(RuntimeError):
    """The provider answered, but its payload did not satisfy the adapter contract."""


class RoleInvocationError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, object]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _clean_content(content: str) -> str:
    text = _THINK_BLOCK.sub("", content or "")
    return text.strip()


def _api_key_headers(service: dict[str, object]) -> dict[str, str]:
    env_name = str(service.get("api_key_env", "") or "").strip()
    if not env_name:
        return {}
    api_key = os.getenv(env_name, "").strip()
    if not api_key:
        return {}
    provider_type = str(service.get("provider_type", "") or "").strip()
    if provider_type == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {api_key}"}


def _post_json(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ProviderResponseError("provider returned a non-object JSON payload")
    return result


def _openai_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in messages
    ]


def _openai_compatible(service: dict[str, object], messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    base_url = str(service.get("base_url", "") or "").rstrip("/")
    model = str(service.get("model", "") or "").strip()
    if not base_url or not model:
        raise ValueError("service base_url and model are required")
    payload: dict[str, object] = {
        "model": model,
        "messages": _openai_messages(messages),
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    response = _post_json(
        f"{base_url}/chat/completions",
        payload,
        headers=_api_key_headers(service),
        timeout=service_request_timeout(service),
    )
    return response


def _ollama(service: dict[str, object], messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    base_url = str(service.get("base_url", "") or "").rstrip("/")
    model = str(service.get("model", "") or "").strip()
    if not base_url or not model:
        raise ValueError("service base_url and model are required")
    payload: dict[str, object] = {
        "model": model,
        "messages": _openai_messages(messages),
        "stream": False,
        "options": {"temperature": temperature},
    }
    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens
    return _post_json(f"{base_url}/api/chat", payload, timeout=service_request_timeout(service))


def _same_service(left: dict[str, object], right: dict[str, object]) -> bool:
    left_key = (
        service_execution_identity(left),
        str(left.get("api_key_env", "") or "").strip(),
    )
    right_key = (
        service_execution_identity(right),
        str(right.get("api_key_env", "") or "").strip(),
    )
    return left_key == right_key


def _service_summary(service: dict[str, object]) -> dict[str, str]:
    summary = {
        name: str(service.get(name, "") or "").strip()
        for name in ("name", "provider_type", "base_url", "model")
    }
    base_url = summary["base_url"]
    try:
        parsed = urllib.parse.urlsplit(base_url)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        summary["base_url"] = urllib.parse.urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, "", ""))
    except ValueError:
        summary["base_url"] = "<invalid-url>"
    return summary


def _error_detail(exc: Exception) -> dict[str, object]:
    status = int(getattr(exc, "code", 0) or 0) if isinstance(exc, urllib.error.HTTPError) else None
    if isinstance(exc, ProviderResponseError):
        category = "response_contract"
    elif isinstance(exc, urllib.error.HTTPError):
        category = "http_server" if 500 <= status < 600 else "http_client"
    elif isinstance(exc, (TimeoutError,)):
        category = "timeout"
    elif isinstance(exc, urllib.error.URLError):
        category = "connection"
    elif isinstance(exc, (ConnectionError, OSError)):
        category = "transport"
    elif isinstance(exc, ValueError):
        category = "configuration"
    else:
        category = "unexpected"
    message = f"HTTP {status}: {getattr(exc, 'reason', '')}" if isinstance(exc, urllib.error.HTTPError) else str(exc)
    return {
        "error_type": type(exc).__name__,
        "error_category": category,
        "message": message[:1000],
        "http_status": status,
        "retryable": _should_retry_with_fallback(exc),
    }


def _openai_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderResponseError("OpenAI-compatible response requires a non-empty choices list")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("OpenAI-compatible response requires choices[0].message")
    content = _clean_content(str(message.get("content", "")))
    if not content:
        raise ProviderResponseError("OpenAI-compatible response content is empty")
    return content


def _ollama_content(response: dict[str, object]) -> str:
    message = response.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("Ollama response requires message")
    content = _clean_content(str(message.get("content", "")))
    if not content:
        raise ProviderResponseError("Ollama response content is empty")
    return content


def _invoke_service(service: dict[str, object], messages: list[dict[str, str]], temperature: float, max_tokens: int | None) -> dict[str, object]:
    provider_type = str(service.get("provider_type", "") or "").strip()
    if provider_type in {"openai_compatible", "openai", "vllm", "codex"}:
        response = _openai_compatible(service, messages, temperature=temperature, max_tokens=max_tokens)
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _openai_content(response),
            "raw": response,
        }
    if provider_type == "ollama":
        response = _ollama(service, messages, temperature=temperature, max_tokens=max_tokens)
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _ollama_content(response),
            "raw": response,
        }
    raise ValueError(f"unsupported provider type: {provider_type}")


def _should_retry_with_fallback(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return 500 <= getattr(exc, "code", 0) < 600
    return isinstance(exc, (ProviderResponseError, urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _invoke_with_retries(
    service: dict[str, object],
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
    retries: int,
    route: str,
    trace: list[dict[str, object]],
) -> dict[str, object]:
    attempts = max(1, retries + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = _invoke_service(service, messages, temperature, max_tokens)
            result["attempt"] = attempt
            trace.append(
                {
                    "route": route,
                    "attempt": attempt,
                    "outcome": "success",
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    "service": _service_summary(service),
                }
            )
            return result
        except Exception as exc:
            trace.append(
                {
                    "route": route,
                    "attempt": attempt,
                    "outcome": "failed",
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    "service": _service_summary(service),
                    **_error_detail(exc),
                }
            )
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            last_exc = exc
            if not _should_retry_with_fallback(exc) or attempt >= attempts:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("unexpected retry failure")


def call_role(
    role: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
) -> dict[str, object]:
    try:
        service = role_service(role)
    except ValueError as exc:
        diagnostics = {
            "role": role,
            "used_fallback": False,
            "selected_service": None,
            "attempts": [],
            "final_error": _error_detail(exc),
        }
        log_event("ai.invocation.failed", role=role, attempts=0, category="configuration")
        raise RoleInvocationError(f"invalid services configuration: {exc}", diagnostics) from exc
    if not service:
        exc = ValueError(f"no service configured for role: {role}")
        diagnostics = {
            "role": role,
            "used_fallback": False,
            "selected_service": None,
            "attempts": [],
            "final_error": _error_detail(exc),
        }
        log_event("ai.invocation.failed", role=role, attempts=0, category="configuration")
        raise RoleInvocationError(str(exc), diagnostics) from exc
    configuration_issues = service_configuration_issues(service)
    if configuration_issues:
        exc = ValueError("; ".join(configuration_issues))
        diagnostics = {
            "role": role,
            "used_fallback": False,
            "selected_service": _service_summary(service),
            "attempts": [],
            "final_error": _error_detail(exc),
        }
        log_event("ai.invocation.failed", role=role, attempts=0, category="configuration")
        raise RoleInvocationError(f"invalid role service configuration: {exc}", diagnostics) from exc
    trace: list[dict[str, object]] = []
    try:
        result = _invoke_with_retries(service, messages, temperature, max_tokens, retries, "primary", trace)
        result["diagnostics"] = {
            "role": role,
            "used_fallback": False,
            "selected_service": _service_summary(service),
            "attempts": trace,
        }
        log_event("ai.invocation.completed", role=role, fallback=False, attempts=len(trace))
        return result
    except Exception as exc:
        if not _should_retry_with_fallback(exc):
            diagnostics = {
                "role": role,
                "used_fallback": False,
                "selected_service": None,
                "attempts": trace,
                "final_error": _error_detail(exc),
            }
            log_event("ai.invocation.failed", role=role, attempts=len(trace), category=diagnostics["final_error"]["error_category"])
            raise RoleInvocationError(f"role service failed: {exc}", diagnostics) from exc
        try:
            fallback = fallback_service()
        except ValueError as fallback_exc:
            diagnostics = {
                "role": role,
                "used_fallback": False,
                "selected_service": None,
                "attempts": trace,
                "primary_error": _error_detail(exc),
                "fallback_configuration": [str(fallback_exc)],
            }
            log_event("ai.invocation.failed", role=role, attempts=len(trace), category="fallback_configuration")
            raise RoleInvocationError(
                f"role service failed and fallback configuration could not be loaded: {fallback_exc}", diagnostics
            ) from exc
        fallback_issues = service_configuration_issues(fallback) if fallback else []
        if fallback and fallback_issues:
            diagnostics = {
                "role": role,
                "used_fallback": False,
                "selected_service": None,
                "attempts": trace,
                "primary_error": _error_detail(exc),
                "fallback_configuration": fallback_issues,
            }
            log_event("ai.invocation.failed", role=role, attempts=len(trace), category="fallback_configuration")
            raise RoleInvocationError(
                "role service failed and fallback service configuration is invalid: " + "; ".join(fallback_issues),
                diagnostics,
            ) from exc
        if fallback and not _same_service(service, fallback):
            try:
                result = _invoke_with_retries(fallback, messages, temperature, max_tokens, retries, "fallback", trace)
                result["fallback_error"] = str(exc)
                result["primary_error"] = str(exc)
                result["diagnostics"] = {
                    "role": role,
                    "used_fallback": True,
                    "fallback_reason": _error_detail(exc),
                    "selected_service": _service_summary(fallback),
                    "attempts": trace,
                }
                log_event("ai.invocation.completed", role=role, fallback=True, attempts=len(trace))
                return result
            except Exception as fallback_exc:
                diagnostics = {
                    "role": role,
                    "used_fallback": True,
                    "selected_service": None,
                    "attempts": trace,
                    "primary_error": _error_detail(exc),
                    "final_error": _error_detail(fallback_exc),
                }
                log_event("ai.invocation.failed", role=role, attempts=len(trace), category=diagnostics["final_error"]["error_category"])
                raise RoleInvocationError(
                    "role service and fallback service both failed: "
                    f"primary={exc!s}; fallback={fallback_exc!s}",
                    diagnostics,
                ) from fallback_exc
        diagnostics = {
            "role": role,
            "used_fallback": False,
            "selected_service": None,
            "attempts": trace,
            "final_error": _error_detail(exc),
        }
        log_event("ai.invocation.failed", role=role, attempts=len(trace), category=diagnostics["final_error"]["error_category"])
        raise RoleInvocationError(f"role service failed: {exc}", diagnostics) from exc


def invoke(
    role: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
) -> dict[str, object]:
    return call_role(
        role,
        build_messages(role, prompt, system=system),
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
    )


def invocation_report(result: dict[str, object]) -> dict[str, object]:
    service = result.get("service", {})
    return {
        "content": result.get("content", ""),
        "provider_type": result.get("provider_type", ""),
        "service": _service_summary(service if isinstance(service, dict) else {}),
        "attempt": result.get("attempt", 1),
        "cache_hit": result.get("cache_hit", False),
        "fallback_error": result.get("fallback_error", ""),
        "primary_error": result.get("primary_error", ""),
        "diagnostics": result.get("diagnostics", {}),
    }
