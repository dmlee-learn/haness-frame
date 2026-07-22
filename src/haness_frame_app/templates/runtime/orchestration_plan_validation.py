from __future__ import annotations

import datetime as dt


def _string_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"orchestration plan {field} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"orchestration plan {field} must not be empty")
    return value


def _validate_created_at(value: object) -> None:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("orchestration plan created_at is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("orchestration plan created_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("orchestration plan created_at must include a timezone")


def _validate_service(service: object) -> None:
    if not isinstance(service, dict):
        raise ValueError("orchestration plan role service must be a JSON object")
    if not isinstance(service.get("assigned"), bool) or not isinstance(service.get("enabled"), bool):
        raise ValueError("orchestration plan role service flags are invalid")
    for field in ("name", "provider_type", "model"):
        if not isinstance(service.get(field), str):
            raise ValueError(f"orchestration plan role service {field} is invalid")


def validate_plan_schema(
    plan: dict[str, object],
    role_order: list[str],
    role_summaries: dict[str, str],
    role_reasons: dict[str, str],
) -> None:
    task = plan.get("task")
    if not isinstance(task, str) or not task.strip() or len(task) > 10000:
        raise ValueError("orchestration plan task is invalid")
    _validate_created_at(plan.get("created_at"))
    _string_list(plan.get("task_tags"), "task_tags")
    recommended = _string_list(plan.get("recommended_roles"), "recommended_roles", allow_empty=False)
    planning = _string_list(plan.get("planning_roles"), "planning_roles", allow_empty=False)
    if len(recommended) != len(set(recommended)) or any(role not in role_order for role in recommended):
        raise ValueError("orchestration plan recommended roles are invalid")
    if recommended != sorted(recommended, key=role_order.index):
        raise ValueError("orchestration plan recommended role order is invalid")
    if any(role not in recommended for role in planning):
        raise ValueError("orchestration plan planning roles are not a recommended subset")

    gate = plan.get("decision_gate")
    if not isinstance(gate, dict) or not isinstance(gate.get("allowed"), bool):
        raise ValueError("orchestration plan decision gate is invalid")
    gate_issues = _string_list(gate.get("issues"), "decision gate issues")
    if gate["allowed"] is not (not gate_issues):
        raise ValueError("orchestration plan decision gate state is inconsistent")

    entries = plan.get("roles")
    if not isinstance(entries, list) or len(entries) != len(recommended):
        raise ValueError("orchestration plan role entries are inconsistent")
    expected_blocked: list[dict[str, object]] = []
    for expected_role, entry in zip(recommended, entries):
        if not isinstance(entry, dict) or entry.get("role") != expected_role:
            raise ValueError("orchestration plan role entry order is inconsistent")
        if entry.get("summary") != role_summaries.get(expected_role):
            raise ValueError("orchestration plan role summary is inconsistent")
        if entry.get("reason") != role_reasons.get(expected_role):
            raise ValueError("orchestration plan role reason is inconsistent")
        blockers = _string_list(entry.get("blockers"), "role blockers")
        service = entry.get("service")
        _validate_service(service)
        expected_blockers = []
        if not service["assigned"]:
            expected_blockers.append("service is not assigned")
        elif not service["enabled"]:
            expected_blockers.append("assigned service is disabled")
        if expected_role in {"coder", "reviewer"} and not gate["allowed"]:
            expected_blockers.append("decision gate is closed")
        if blockers != expected_blockers:
            raise ValueError("orchestration plan role blockers are inconsistent")
        if entry.get("currently_invocable") is not (not expected_blockers):
            raise ValueError("orchestration plan role invocability is inconsistent")
        if blockers:
            expected_blocked.append({"role": expected_role, "blockers": blockers})
    if plan.get("blocked_roles") != expected_blocked:
        raise ValueError("orchestration plan blocked role summary is inconsistent")

    commands = _string_list(plan.get("recommended_commands"), "recommended_commands")
    if len(commands) > 50 or any(len(command) > 1000 for command in commands):
        raise ValueError("orchestration plan recommended commands exceed limits")
