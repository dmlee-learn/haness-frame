from __future__ import annotations

import json

from .audit import log_event
from .scorecard import mark_check
from .workflow import run_sequence

DEFAULT_DEBATE_ROLES = ["planner", "designer", "architect", "critic", "decision_maker"]


def run_debate(
    prompt: str,
    roles: list[str] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    retries: int = 1,
) -> list[dict[str, object]]:
    selected_roles = roles or DEFAULT_DEBATE_ROLES
    log_event("debate.started", roles=selected_roles, prompt=prompt[:200])
    outputs = run_sequence(
        selected_roles,
        prompt,
        system="Run this as a structured design debate. Each role must answer with decisions, risks, and unresolved questions.",
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
    )
    mark_check("debate", True, f"{len(outputs)} role output(s)")
    log_event("debate.completed", roles=selected_roles, outputs=len(outputs))
    return outputs


def debate_summary(outputs: list[dict[str, object]]) -> str:
    return json.dumps(
        [{"role": item.get("role", ""), "content": item.get("content", "")} for item in outputs],
        indent=2,
        ensure_ascii=False,
    )
