from __future__ import annotations

import json

from .storage import read_text


def load_services() -> dict[str, object]:
    payload = read_text("workspace/services.json", "{}")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


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
