from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import time
from collections.abc import Callable

from .audit import log_event
from .client import invoke
from .services import (
    fallback_service,
    role_service,
    service_configuration_issues,
    service_execution_identity,
)
from . import storage
from .storage import file_lock, operation_lock, read_text, write_text

CACHE_ROOT = "workspace/cache/ai"
CACHE_FORMAT_VERSION = 2


def _result_sha256(key: str, role: str, result: dict[str, object]) -> str:
    payload = {"cache_key": key, "role": role, "result": result}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_paths() -> list[pathlib.Path]:
    root = storage.ROOT / CACHE_ROOT
    return sorted(root.glob("*.json")) if root.is_dir() else []


def _entry_state(path: pathlib.Path, max_age_seconds: int) -> tuple[str, int]:
    try:
        size = path.stat().st_size
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid", 0
    if not isinstance(payload, dict):
        return "invalid", size
    created_epoch = payload.get("created_epoch")
    result = payload.get("result")
    role = payload.get("role")
    key = path.stem
    if (
        payload.get("format_version") != CACHE_FORMAT_VERSION
        or payload.get("cache_key") != key
        or not isinstance(role, str)
        or not role.strip()
        or not isinstance(created_epoch, (int, float))
        or not isinstance(result, dict)
        or not str(result.get("content", "")).strip()
        or payload.get("result_sha256") != _result_sha256(key, role, result)
    ):
        return "invalid", size
    if time.time() - created_epoch > max_age_seconds:
        return "stale", size
    return "fresh", size


def cache_status(max_age_seconds: int = 86400) -> dict[str, object]:
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be at least 1")
    counts = {"fresh": 0, "stale": 0, "invalid": 0}
    total_bytes = 0
    for path in _cache_paths():
        state, size = _entry_state(path, max_age_seconds)
        counts[state] += 1
        total_bytes += size
    return {
        "entries": sum(counts.values()),
        **counts,
        "total_bytes": total_bytes,
        "max_age_seconds": max_age_seconds,
    }


def prune_cache(max_age_seconds: int = 86400, *, include_fresh: bool = False) -> dict[str, object]:
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be at least 1")
    removed = {"fresh": 0, "stale": 0, "invalid": 0}
    removed_bytes = 0
    for path in _cache_paths():
        key = path.stem
        with operation_lock("ai-cache", key, timeout=300.0):
            if not path.is_file():
                continue
            state, size = _entry_state(path, max_age_seconds)
            if state == "fresh" and not include_fresh:
                continue
            with file_lock(path):
                if path.is_file():
                    path.unlink()
            removed[state] += 1
            removed_bytes += size
    report = {
        "removed": sum(removed.values()),
        "removed_by_state": removed,
        "removed_bytes": removed_bytes,
        "include_fresh": include_fresh,
        "remaining": cache_status(max_age_seconds),
    }
    log_event("ai.cache.pruned", **report)
    return report


def _service_identity(service: dict[str, object]) -> dict[str, object]:
    provider, base_url, model = service_execution_identity(service)
    return {
        "name": str(service.get("name", "") or "").strip(),
        "provider_type": provider,
        "model": model,
        "base_url": base_url,
        "api_key_env": str(service.get("api_key_env", "") or "").strip(),
        "enabled": service.get("enabled", True),
    }


def _cache_service_identity(service: dict[str, object]) -> dict[str, object]:
    identity = _service_identity(service)
    identity.pop("name", None)
    env_name = str(identity["api_key_env"])
    credential = os.getenv(env_name, "") if env_name else ""
    identity["credential_sha256"] = hashlib.sha256(credential.encode("utf-8")).hexdigest() if credential else ""
    identity["configuration_issues"] = service_configuration_issues(service) if service else []
    return identity


def cache_key(
    role: str,
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    payload = {
        "version": 2,
        "role": role,
        "prompt": prompt,
        "system": system,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "service": _cache_service_identity(role_service(role)),
        "fallback": _cache_service_identity(fallback_service()),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_cache(
    key: str,
    max_age_seconds: int,
    content_validator: Callable[[str], str] | None = None,
) -> dict[str, object] | None:
    text = read_text(f"{CACHE_ROOT}/{key}.json", "")
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    created_epoch = payload.get("created_epoch")
    if not isinstance(created_epoch, (int, float)) or time.time() - created_epoch > max_age_seconds:
        return None
    result = payload.get("result")
    role = payload.get("role")
    if (
        payload.get("format_version") != CACHE_FORMAT_VERSION
        or payload.get("cache_key") != key
        or not isinstance(role, str)
        or not role.strip()
        or not isinstance(result, dict)
        or not str(result.get("content", "")).strip()
        or payload.get("result_sha256") != _result_sha256(key, role, result)
    ):
        return None
    restored = dict(result)
    if content_validator is not None:
        try:
            restored["content"] = content_validator(str(restored.get("content", "")))
        except ValueError:
            return None
    restored["cache_hit"] = True
    restored["cache_key"] = key
    return restored


def _save_cache(key: str, role: str, result: dict[str, object]) -> None:
    safe_result = {
        name: result.get(name, "")
        for name in (
            "provider_type",
            "content",
            "attempt",
            "fallback_error",
            "primary_error",
            "diagnostics",
        )
    }
    safe_result["service"] = _service_identity(result.get("service", {}) if isinstance(result.get("service"), dict) else {})
    payload = {
        "format_version": CACHE_FORMAT_VERSION,
        "cache_key": key,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "created_epoch": time.time(),
        "role": role,
        "result": safe_result,
        "result_sha256": _result_sha256(key, role, safe_result),
    }
    write_text(f"{CACHE_ROOT}/{key}.json", json.dumps(payload, indent=2, ensure_ascii=False))


def invoke_cached(
    role: str,
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
    enabled: bool = True,
    max_age_seconds: int = 86400,
    singleflight_timeout_seconds: float = 300.0,
    content_validator: Callable[[str], str] | None = None,
    invoke_fn: Callable[..., dict[str, object]] | None = None,
) -> dict[str, object]:
    key = cache_key(
        role,
        prompt,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    provider = invoke_fn or invoke

    def call_provider() -> dict[str, object]:
        result = dict(
            provider(
                role,
                prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
            )
        )
        if content_validator is not None:
            result["content"] = content_validator(str(result.get("content", "")))
        result["cache_hit"] = False
        result["cache_key"] = key
        return result

    if not enabled:
        return call_provider()

    max_age = max(1, max_age_seconds)
    cached = _load_cache(key, max_age, content_validator)
    if cached is not None:
        log_event("ai.cache.hit", role=role, cache_key=key)
        return cached

    with operation_lock("ai-cache", key, timeout=max(0.0, singleflight_timeout_seconds)):
        cached = _load_cache(key, max_age, content_validator)
        if cached is not None:
            log_event("ai.cache.hit", role=role, cache_key=key, waited=True)
            return cached
        result = call_provider()
        if str(result.get("content", "")).strip():
            _save_cache(key, role, result)
            log_event("ai.cache.saved", role=role, cache_key=key)
        return result
