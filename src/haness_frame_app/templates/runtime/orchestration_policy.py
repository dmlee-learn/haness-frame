from __future__ import annotations

import json

from .storage import read_text

POLICY_FILE = "workspace/orchestration-policy.json"
DEFAULTS = {
    "max_roles": 16,
    "max_prompt_chars": 20000,
    "max_system_chars": 40000,
    "max_context_chars": 60000,
    "min_output_chars": 20,
    "max_output_chars": 100000,
    "max_elapsed_seconds": 1800,
    "max_ai_calls": 16,
    "max_debate_rounds": 5,
    "max_debate_elapsed_seconds": 3600,
    "max_debate_ai_calls": 32,
    "require_independent_debate_judge_service": False,
}


def _bounded_int(payload: dict[str, object], name: str, minimum: int, maximum: int) -> int:
    value = payload.get(name, DEFAULTS[name])
    if isinstance(value, bool):
        raise ValueError(f"orchestration policy {name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"orchestration policy {name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"orchestration policy {name} must be between {minimum} and {maximum}")
    return parsed


def load_orchestration_policy() -> dict[str, object]:
    try:
        payload = json.loads(read_text(POLICY_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid orchestration policy JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("orchestration policy must be a JSON object")
    strict_judge = payload.get(
        "require_independent_debate_judge_service",
        DEFAULTS["require_independent_debate_judge_service"],
    )
    if not isinstance(strict_judge, bool):
        raise ValueError("orchestration policy require_independent_debate_judge_service must be a boolean")
    policy = {
        "max_roles": _bounded_int(payload, "max_roles", 1, 100),
        "max_prompt_chars": _bounded_int(payload, "max_prompt_chars", 100, 1000000),
        "max_system_chars": _bounded_int(payload, "max_system_chars", 100, 1000000),
        "max_context_chars": _bounded_int(payload, "max_context_chars", 1000, 2000000),
        "min_output_chars": _bounded_int(payload, "min_output_chars", 1, 10000),
        "max_output_chars": _bounded_int(payload, "max_output_chars", 100, 2000000),
        "max_elapsed_seconds": _bounded_int(payload, "max_elapsed_seconds", 1, 86400),
        "max_ai_calls": _bounded_int(payload, "max_ai_calls", 1, 1000),
        "max_debate_rounds": _bounded_int(payload, "max_debate_rounds", 1, 20),
        "max_debate_elapsed_seconds": _bounded_int(payload, "max_debate_elapsed_seconds", 1, 86400),
        "max_debate_ai_calls": _bounded_int(payload, "max_debate_ai_calls", 1, 2000),
        "require_independent_debate_judge_service": strict_judge,
    }
    if policy["min_output_chars"] > policy["max_output_chars"]:
        raise ValueError("orchestration policy min_output_chars must not exceed max_output_chars")
    return policy
