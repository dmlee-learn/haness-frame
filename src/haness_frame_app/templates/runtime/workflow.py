from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .audit import log_event
from .client import invoke
from .engine import enforce_decision_gate
from .roles import ROLE_ORDER
from .scorecard import mark_check
from .storage import ensure_workspace, write_text


def normalize_roles(roles: list[str]) -> list[str]:
    normalized = [role.strip() for role in roles if role.strip()]
    unknown = [role for role in normalized if role not in ROLE_ORDER]
    if unknown:
        raise ValueError(f"unknown role(s): {', '.join(unknown)}")
    if len(normalized) != len(set(normalized)):
        raise ValueError("role sequence contains duplicate roles")
    return normalized


def validate_role_sequence(roles: list[str]) -> None:
    positions = {role: ROLE_ORDER.index(role) for role in ROLE_ORDER}
    for previous, current in zip(roles, roles[1:]):
        if positions[current] < positions[previous]:
            raise ValueError(f"role sequence moves backward: {previous} -> {current}")


def run_sequence(
    roles: list[str],
    prompt: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
) -> list[dict[str, object]]:
    ensure_workspace()
    log_event("pipeline.started", roles=roles, prompt=prompt[:200])
    try:
        roles = normalize_roles(roles)
        validate_role_sequence(roles)
    except Exception as exc:
        mark_check("pipeline", False, str(exc))
        log_event("pipeline.failed", error=str(exc), stage="validate")
        raise
    outputs: list[dict[str, object]] = []
    context = system.strip()
    execution_dir = Path("workspace") / "executions"
    execution_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, role in enumerate(roles, start=1):
            enforce_decision_gate(role)
            log_event("pipeline.role.started", index=index, role=role)
            result = invoke(
                role,
                prompt,
                system=context,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
            )
            payload = {
                "index": index,
                "role": role,
                "prompt": prompt,
                "system": context,
                "provider_type": result.get("provider_type", ""),
                "service": result.get("service", {}),
                "attempt": result.get("attempt", 1),
                "content": result.get("content", ""),
                "fallback_error": result.get("fallback_error", ""),
                "primary_error": result.get("primary_error", ""),
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
            safe_role = role.replace("/", "-")
            write_text(f"workspace/executions/{index:02d}-{safe_role}.json", json.dumps(payload, indent=2, ensure_ascii=False))
            write_text(
                f"workspace/executions/{index:02d}-{safe_role}.md",
                f"# {role}\n\n{result.get('content', '')}\n",
            )
            outputs.append(payload)
            log_event("pipeline.role.completed", index=index, role=role, provider_type=payload["provider_type"])
            context = "\n\n".join(
                part
                for part in [
                    context,
                    f"Previous role ({role}) output:\n{result.get('content', '')}",
                ]
                if part
            )
    except Exception as exc:
        mark_check("pipeline", False, str(exc))
        log_event("pipeline.failed", error=str(exc), stage="execute")
        raise
    write_text(
        "workspace/executions/latest.json",
        json.dumps(
            {
                "prompt": prompt,
                "system": system,
                "roles": roles,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "results": outputs,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    mark_check("pipeline", True, f"{len(outputs)} role output(s)")
    log_event("pipeline.completed", roles=roles, outputs=len(outputs))
    return outputs
