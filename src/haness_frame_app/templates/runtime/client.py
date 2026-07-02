from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .prompting import build_messages
from .services import fallback_service, role_service


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


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


def _post_json(url: str, payload: dict[str, object], headers: dict[str, str] | None = None, timeout: int = 20) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
    return _post_json(f"{base_url}/api/chat", payload)


def _same_service(left: dict[str, object], right: dict[str, object]) -> bool:
    return (
        str(left.get("name", "")) == str(right.get("name", ""))
        and str(left.get("provider_type", "")) == str(right.get("provider_type", ""))
        and str(left.get("base_url", "")) == str(right.get("base_url", ""))
        and str(left.get("model", "")) == str(right.get("model", ""))
    )


def _invoke_service(service: dict[str, object], messages: list[dict[str, str]], temperature: float, max_tokens: int | None) -> dict[str, object]:
    provider_type = str(service.get("provider_type", "") or "").strip()
    if provider_type in {"openai_compatible", "openai", "vllm", "codex"}:
        response = _openai_compatible(service, messages, temperature=temperature, max_tokens=max_tokens)
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _clean_content(str(message.get("content", ""))),
            "raw": response,
        }
    if provider_type == "ollama":
        response = _ollama(service, messages, temperature=temperature, max_tokens=max_tokens)
        message = response.get("message") or {}
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _clean_content(str(message.get("content", ""))),
            "raw": response,
        }
    raise ValueError(f"unsupported provider type: {provider_type}")


def _should_retry_with_fallback(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return 500 <= getattr(exc, "code", 0) < 600
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _invoke_with_retries(
    service: dict[str, object],
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None,
    retries: int,
) -> dict[str, object]:
    attempts = max(1, retries + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = _invoke_service(service, messages, temperature, max_tokens)
            result["attempt"] = attempt
            return result
        except Exception as exc:
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
    service = role_service(role)
    if not service:
        raise ValueError(f"no service configured for role: {role}")
    try:
        return _invoke_with_retries(service, messages, temperature, max_tokens, retries)
    except Exception as exc:
        if not _should_retry_with_fallback(exc):
            raise
        fallback = fallback_service()
        if fallback and not _same_service(service, fallback):
            try:
                result = _invoke_with_retries(fallback, messages, temperature, max_tokens, retries)
                result["fallback_error"] = str(exc)
                result["primary_error"] = str(exc)
                return result
            except Exception as fallback_exc:
                raise RuntimeError(
                    "role service and fallback service both failed: "
                    f"primary={exc!s}; fallback={fallback_exc!s}"
                ) from fallback_exc
        raise


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
