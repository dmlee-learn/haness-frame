from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

from .audit import log_event
from .engine import decision_gate
from .debate import abandon_debate_rounds, load_debate_session, resume_debate_rounds, run_debate_rounds
from .repair import abandon_repair_loop, load_repair_session, resume_repair_loop, run_repair_loop
from .orchestration_plan_validation import validate_plan_schema
from .orchestration_policy import load_orchestration_policy
from .roles import ROLE_ORDER, describe_role
from .services import load_services
from .storage import operation_lock, read_latest_session, read_text, write_text
from .workflow import abandon_sequence, load_pipeline_session, resume_sequence, run_sequence

PLAN_ROOT = "workspace/orchestration"
EXECUTION_ROOT = f"{PLAN_ROOT}/executions"
LATEST_EXECUTION = f"{PLAN_ROOT}/latest-execution.json"
PLANNING_SYSTEM = "Produce an evidence-aware implementation plan with decisions, risks, and verification needs."
_EXECUTION_ID = re.compile(r"^orchestration-\d{8}T\d{12}Z$")
_PLAN_ID = re.compile(r"^\d{8}T\d{12}Z$")
_CHILD_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")

_SIGNALS = {
    "research": (
        "research", "evidence", "compare", "latest", "source", "investigate",
        "조사", "근거", "비교", "최신", "출처", "검증",
    ),
    "bugfix": (
        "bug", "fix", "error", "failure", "crash", "broken", "debug",
        "버그", "오류", "실패", "고장", "디버그", "수정",
    ),
    "ui": (
        "ui", "ux", "screen", "frontend", "layout", "design",
        "화면", "사용자 경험", "프론트", "레이아웃", "디자인",
    ),
    "architecture": (
        "architecture", "api", "integration", "database", "migration",
        "performance", "scalability", "아키텍처", "연동", "데이터베이스",
        "마이그레이션", "성능", "확장성",
    ),
    "implementation": (
        "build", "implement", "create", "add", "change", "refactor", "develop",
        "만들", "구현", "개발", "추가", "변경", "리팩터",
    ),
    "high_risk": (
        "security", "authentication", "authorization", "payment", "privacy",
        "production", "delete", "credential", "보안", "인증", "권한", "결제",
        "개인정보", "운영 환경", "삭제", "자격 증명",
    ),
}

_ROLE_REASONS = {
    "project_scout": "Find comparable systems and known failure modes.",
    "context_curator": "Assemble project constraints before proposing work.",
    "researcher": "Collect traceable evidence for claims and risks.",
    "planner": "Turn context into an ordered implementation decision.",
    "designer": "Define user-facing flows and interaction constraints.",
    "architect": "Evaluate boundaries, integration, data, and operational risks.",
    "critic": "Challenge assumptions, scope, and missing verification.",
    "debugger": "Diagnose the observed failure before changing files.",
    "decision_maker": "Produce one accepted direction and implementation brief.",
    "coder": "Implement only the accepted, decision-gated change.",
    "reviewer": "Independently evaluate tests, patch, and remaining risks.",
    "escalation": "Review high-impact decisions that need additional judgment.",
}


def _contains(text: str, term: str) -> bool:
    if term.isascii() and re.fullmatch(r"[a-z0-9_ -]+", term):
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text))
    return term in text


def classify_task(task: str) -> list[str]:
    normalized = task.strip().lower()
    if not normalized:
        raise ValueError("task must be a non-empty string")
    if len(normalized) > 10000:
        raise ValueError("task must not exceed 10000 characters")
    return [name for name, terms in _SIGNALS.items() if any(_contains(normalized, term) for term in terms)]


def recommend_roles(task: str) -> tuple[list[str], list[str]]:
    tags = classify_task(task)
    selected = {"context_curator", "planner", "critic", "decision_maker"}
    if "research" in tags or "architecture" in tags or "high_risk" in tags:
        selected.update({"project_scout", "researcher"})
    if "ui" in tags:
        selected.add("designer")
    if "architecture" in tags or "high_risk" in tags:
        selected.add("architect")
    if "implementation" in tags or "bugfix" in tags:
        selected.update({"debugger", "coder", "reviewer"})
    if "high_risk" in tags:
        selected.add("escalation")
    return tags, [role for role in ROLE_ORDER if role in selected]


def _service_status(role: str, role_services: dict[str, object]) -> dict[str, object]:
    service = role_services.get(role, {})
    if not isinstance(service, dict) or not service:
        return {"assigned": False, "enabled": False, "name": "", "provider_type": "", "model": ""}
    return {
        "assigned": True,
        "enabled": bool(service.get("enabled", True)),
        "name": str(service.get("name", "") or ""),
        "provider_type": str(service.get("provider_type", "") or ""),
        "model": str(service.get("model", "") or ""),
    }


def _recommended_commands(tags: list[str], planning_roles: list[str]) -> list[str]:
    commands = []
    if "research" in tags or "architecture" in tags or "high_risk" in tags:
        commands.append("python app.py search-plan")
    if planning_roles:
        commands.append(f"python app.py pipeline --roles {','.join(planning_roles)} --prompt TASK")
    commands.extend(["python app.py decision-draft", "python app.py gate"])
    if "implementation" in tags or "bugfix" in tags:
        commands.append("python app.py repair-run --task TASK")
    return commands


def build_role_plan(task: str) -> dict[str, object]:
    task = task.strip()
    tags, roles = recommend_roles(task)
    services = load_services()
    role_services = services.get("role_services", {})
    if not isinstance(role_services, dict):
        role_services = {}
    gate = decision_gate()
    role_entries = []
    blocked_roles = []
    for role in roles:
        service = _service_status(role, role_services)
        blockers = []
        if not service["assigned"]:
            blockers.append("service is not assigned")
        elif not service["enabled"]:
            blockers.append("assigned service is disabled")
        if role in {"coder", "reviewer"} and not gate["allowed"]:
            blockers.append("decision gate is closed")
        entry = {
            "role": role,
            "summary": describe_role(role),
            "reason": _ROLE_REASONS[role],
            "service": service,
            "currently_invocable": not blockers,
            "blockers": blockers,
        }
        role_entries.append(entry)
        if blockers:
            blocked_roles.append({"role": role, "blockers": blockers})

    planning_roles = [
        role for role in roles
        if ROLE_ORDER.index(role) <= ROLE_ORDER.index("decision_maker") and role != "debugger"
    ]
    commands = _recommended_commands(tags, planning_roles)

    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    plan = {
        "format_version": 2,
        "created_at": created_at,
        "task": task,
        "task_tags": tags,
        "recommended_roles": roles,
        "planning_roles": planning_roles,
        "roles": role_entries,
        "blocked_roles": blocked_roles,
        "decision_gate": {"allowed": gate["allowed"], "issues": gate["issues"]},
        "recommended_commands": commands,
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    plan["plan_id"] = stamp
    plan["plan_sha256"] = orchestration_plan_sha256(plan)
    payload = json.dumps(plan, indent=2, ensure_ascii=False)
    write_text(f"{PLAN_ROOT}/{stamp}.json", payload)
    write_text(f"{PLAN_ROOT}/latest.json", payload)
    task_hash = hashlib.sha256(task.encode("utf-8")).hexdigest()
    log_event("orchestration.plan.created", task_sha256=task_hash, tags=tags, roles=roles, blocked=len(blocked_roles))
    return plan


def orchestration_plan_sha256(plan: dict[str, object]) -> str:
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def orchestration_execution_sha256(execution: dict[str, object]) -> str:
    payload = {key: value for key, value in execution.items() if key != "execution_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _save_execution(execution: dict[str, object]) -> None:
    if execution.get("format_version") == 2:
        execution["execution_sha256"] = orchestration_execution_sha256(execution)
    payload = json.dumps(execution, indent=2, ensure_ascii=False)
    execution_id = str(execution["execution_id"])
    write_text(f"{EXECUTION_ROOT}/{execution_id}/session.json", payload)
    write_text(LATEST_EXECUTION, payload)


def _validate_execution_options(options: dict[str, object]) -> None:
    rounds = options.get("rounds")
    retries = options.get("retries")
    max_attempts = options.get("max_attempts")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 20:
        raise ValueError("orchestration execution rounds must be an integer between 1 and 20")
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 20:
        raise ValueError("orchestration execution retries must be an integer between 0 and 20")
    if max_attempts is not None and (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or not 1 <= max_attempts <= 10
    ):
        raise ValueError("orchestration execution max_attempts must be null or an integer between 1 and 10")


def _validate_child_status(stage: str, status: str, child_status: str) -> None:
    active = {
        "planning": {"reserved", "not_started", "pending", "running"},
        "debate": {"reserved", "not_started", "pending", "running"},
        "repair": {"reserved", "not_started", "running", "resumed"},
    }[stage]
    success = {
        "planning": {"completed"},
        "debate": {"completed"},
        "repair": {"approved", "already_verified"},
    }[stage]
    failures = {
        "planning": {"failed", "budget_exhausted", "abandoned"},
        "debate": {"failed", "stale", "budget_exhausted", "abandoned"},
        "repair": {
            "failed", "attempts_exhausted", "budget_exhausted", "rollback_blocked",
            "abandoned", "superseded",
        },
    }[stage]
    allowed = active | success | failures
    if child_status not in allowed:
        raise ValueError("orchestration execution child status is invalid")
    consistent = {
        "running": active,
        "completed": success,
        "failed": failures,
        "abandoned": {"not_started", "abandoned", "superseded"},
    }[status]
    if child_status not in consistent:
        raise ValueError("orchestration execution and child statuses are inconsistent")


def _parse_checkpoint_time(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError(f"orchestration execution {field} is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"orchestration execution {field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"orchestration execution {field} must include a timezone")
    return parsed


def _validate_execution_lifecycle(execution: dict[str, object], status: str) -> None:
    created = _parse_checkpoint_time(execution.get("created_at"), "created_at")
    updated = _parse_checkpoint_time(execution.get("updated_at"), "updated_at")
    if updated < created:
        raise ValueError("orchestration execution updated_at precedes created_at")
    error = execution.get("error")
    if not isinstance(error, str) or len(error) > 1000:
        raise ValueError("orchestration execution error is invalid")
    if status in {"running", "completed"} and error:
        raise ValueError(f"{status} orchestration execution must not contain an error")
    if status == "failed" and not error:
        raise ValueError("failed orchestration execution must contain an error")
    if status == "abandoned":
        reason = execution.get("abandonment_reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("abandoned orchestration execution reason is invalid")
        abandoned = _parse_checkpoint_time(execution.get("abandoned_at"), "abandoned_at")
        if not created <= abandoned <= updated:
            raise ValueError("orchestration execution abandoned_at is outside its lifecycle")


def load_orchestration_execution(execution_id: str = "latest") -> dict[str, object]:
    if execution_id == "latest":
        text = read_latest_session(LATEST_EXECUTION, EXECUTION_ROOT, "")
    else:
        if not _EXECUTION_ID.fullmatch(execution_id):
            raise ValueError("invalid orchestration execution id")
        text = read_text(f"{EXECUTION_ROOT}/{execution_id}/session.json", "")
    if not text:
        raise ValueError(f"orchestration execution not found: {execution_id}")
    try:
        execution = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid orchestration execution JSON: {execution_id}") from exc
    if not isinstance(execution, dict):
        raise ValueError("orchestration execution must be a JSON object")
    stored_id = str(execution.get("execution_id", ""))
    if not _EXECUTION_ID.fullmatch(stored_id):
        raise ValueError("stored orchestration execution id is invalid")
    if execution_id != "latest" and stored_id != execution_id:
        raise ValueError("orchestration execution id does not match its checkpoint path")
    format_version = execution.get("format_version", 1)
    if not isinstance(format_version, int) or isinstance(format_version, bool) or format_version not in {1, 2}:
        raise ValueError("orchestration execution format version is unsupported")
    if format_version == 2:
        if execution.get("execution_sha256") != orchestration_execution_sha256(execution):
            raise ValueError("orchestration execution provenance hash mismatch")
        stage = str(execution.get("stage", ""))
        if stage not in {"planning", "debate", "repair"}:
            raise ValueError("orchestration execution stage is invalid")
        status = str(execution.get("status", ""))
        if status not in {"running", "failed", "completed", "abandoned"}:
            raise ValueError("orchestration execution status is invalid")
        _validate_execution_lifecycle(execution, status)
        roles = execution.get("roles")
        options = execution.get("options")
        link = execution.get("linked_session")
        if not isinstance(roles, list) or not roles or not all(isinstance(role, str) for role in roles):
            raise ValueError("orchestration execution roles are invalid")
        if not isinstance(options, dict) or not isinstance(link, dict):
            raise ValueError("orchestration execution options or child link is invalid")
        _validate_execution_options(options)
        expected_kind = "pipeline" if stage == "planning" else stage
        child_kind = str(link.get("kind", ""))
        child_id = str(link.get("id", ""))
        if child_kind != expected_kind or not _CHILD_ID.fullmatch(child_id):
            raise ValueError("orchestration execution child identity is inconsistent")
        task_sha = str(execution.get("task_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", task_sha):
            raise ValueError("orchestration execution task hash is invalid")
        execution_stamp = stored_id.removeprefix("orchestration-")
        expected_child_id = (
            f"pipeline-{execution_stamp}-{task_sha[:10]}"
            if stage == "planning"
            else execution_stamp
        )
        if child_id != expected_child_id:
            raise ValueError("orchestration execution child id does not match its reservation")
        plan = _load_execution_plan(execution)
        if roles != _stage_roles(plan, stage):
            raise ValueError("orchestration execution roles do not match its plan and stage")
        child_status = str(link.get("status", ""))
        _validate_child_status(stage, status, child_status)
    return execution


def abandon_orchestration_execution(execution_id: str, reason: str) -> dict[str, object]:
    resolved_id = str(load_orchestration_execution(execution_id)["execution_id"])
    with operation_lock("orchestration", resolved_id):
        return _abandon_orchestration_execution_unlocked(resolved_id, reason)


def _abandon_orchestration_execution_unlocked(execution_id: str, reason: str) -> dict[str, object]:
    execution = load_orchestration_execution(execution_id)
    if execution.get("status") == "completed":
        raise ValueError("completed orchestration execution cannot be abandoned")
    if execution.get("status") == "abandoned":
        return execution
    reason = reason.strip()
    if not reason:
        raise ValueError("orchestration abandonment reason is required")
    if len(reason) > 1000:
        raise ValueError("orchestration abandonment reason must not exceed 1000 characters")
    link = execution.get("linked_session", {})
    if not isinstance(link, dict):
        raise ValueError("orchestration execution child link is invalid")
    child_kind = str(link.get("kind", ""))
    child_id = str(link.get("id", ""))
    if not child_id:
        raise ValueError("orchestration execution child session id is missing")
    if _child_checkpoint_exists(child_kind, child_id):
        child = _abandon_child_session(child_kind, child_id, reason)
        execution["linked_session"] = {
            "kind": child_kind,
            "id": child_id,
            "status": str(child.get("status", "abandoned")),
        }
    else:
        execution["linked_session"] = {"kind": child_kind, "id": child_id, "status": "not_started"}
    execution["status"] = "abandoned"
    execution["abandonment_reason"] = reason
    execution["abandoned_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    execution["updated_at"] = execution["abandoned_at"]
    _save_execution(execution)
    log_event(
        "orchestration.execution.abandoned",
        execution_id=execution["execution_id"],
        stage=execution.get("stage", ""),
        reason_sha256=hashlib.sha256(reason.encode("utf-8")).hexdigest(),
    )
    return execution


def _abandon_child_session(kind: str, session_id: str, reason: str) -> dict[str, object]:
    if kind == "pipeline":
        return abandon_sequence(session_id, reason)
    if kind == "debate":
        return abandon_debate_rounds(session_id, reason)
    if kind == "repair":
        return abandon_repair_loop(session_id, reason)
    raise ValueError(f"unknown orchestration child kind: {kind}")


def _load_execution_plan(execution: dict[str, object]) -> dict[str, object]:
    plan_id = str(execution.get("plan_id", ""))
    if not _PLAN_ID.fullmatch(plan_id):
        raise ValueError("orchestration execution plan id is invalid")
    text = read_text(f"{PLAN_ROOT}/{plan_id}.json", "")
    if not text:
        raise ValueError(f"orchestration execution plan not found: {plan_id}")
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid orchestration plan JSON: {plan_id}") from exc
    if not isinstance(plan, dict) or str(plan.get("plan_id", "")) != plan_id:
        raise ValueError("orchestration execution plan identity is invalid")
    if plan.get("format_version") != 2:
        raise ValueError("orchestration execution plan format version is unsupported")
    plan_hash = str(plan.get("plan_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", plan_hash):
        raise ValueError("orchestration execution plan hash is invalid")
    if plan_hash != orchestration_plan_sha256(plan):
        raise ValueError("orchestration execution plan provenance hash mismatch")
    if plan_hash != str(execution.get("plan_sha256", "")):
        raise ValueError("orchestration execution plan hash does not match its checkpoint")
    task = str(plan.get("task", ""))
    validate_plan_schema(
        plan,
        ROLE_ORDER,
        {role: describe_role(role) for role in ROLE_ORDER},
        _ROLE_REASONS,
    )
    expected_tags, expected_roles = recommend_roles(task)
    if plan.get("task_tags") != expected_tags:
        raise ValueError("orchestration plan task tags do not match its task")
    if plan.get("recommended_roles") != expected_roles:
        raise ValueError("orchestration plan recommended roles do not match its task")
    expected_planning = [
        role for role in expected_roles
        if ROLE_ORDER.index(role) <= ROLE_ORDER.index("decision_maker") and role != "debugger"
    ]
    if plan.get("planning_roles") != expected_planning:
        raise ValueError("orchestration plan planning roles do not match its task")
    if plan.get("recommended_commands") != _recommended_commands(expected_tags, expected_planning):
        raise ValueError("orchestration plan recommended commands do not match its task")
    task_hash = hashlib.sha256(task.encode("utf-8")).hexdigest()
    if task_hash != str(execution.get("task_sha256", "")):
        raise ValueError("orchestration execution task hash does not match its plan")
    return plan


def _child_checkpoint_exists(kind: str, session_id: str) -> bool:
    roots = {
        "pipeline": f"workspace/executions/runs/{session_id}/session.json",
        "debate": f"workspace/debates/{session_id}/session.json",
        "repair": f"workspace/repairs/{session_id}/session.json",
    }
    path = roots.get(kind, "")
    if not path:
        raise ValueError(f"unknown orchestration child kind: {kind}")
    return bool(read_text(path, ""))


def _load_child_session(kind: str, session_id: str) -> dict[str, object]:
    if kind == "pipeline":
        return load_pipeline_session(session_id)
    if kind == "debate":
        return load_debate_session(session_id)
    if kind == "repair":
        return load_repair_session(session_id)
    raise ValueError(f"unknown orchestration child kind: {kind}")


def reconcile_orchestration_execution(execution_id: str) -> dict[str, object]:
    resolved_id = str(load_orchestration_execution(execution_id)["execution_id"])
    with operation_lock("orchestration", resolved_id):
        execution = load_orchestration_execution(resolved_id)
        if execution.get("status") in {"completed", "abandoned"}:
            return execution
        link = execution.get("linked_session", {})
        if not isinstance(link, dict):
            raise ValueError("orchestration execution child link is invalid")
        kind = str(link.get("kind", ""))
        child_id = str(link.get("id", ""))
        if not child_id:
            raise ValueError("orchestration execution child session id is missing")
        if not _child_checkpoint_exists(kind, child_id):
            execution["linked_session"] = {"kind": kind, "id": child_id, "status": "not_started"}
            execution["status"] = "running"
            execution["error"] = ""
            execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
            _save_execution(execution)
            return execution

        child = _load_child_session(kind, child_id)
        child_status = str(child.get("status", "unknown"))
        success = {
            "pipeline": {"completed"},
            "debate": {"completed"},
            "repair": {"approved", "already_verified"},
        }[kind]
        abandoned = {"abandoned", "superseded"} if kind == "repair" else {"abandoned"}
        active = {"pending", "running", "resumed"}
        execution["linked_session"] = {"kind": kind, "id": child_id, "status": child_status}
        if child_status in success:
            execution["status"] = "completed"
            execution["error"] = ""
        elif child_status in abandoned:
            execution["status"] = "abandoned"
            execution["abandonment_reason"] = f"linked child session is {child_status}"
            execution["abandoned_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
        elif child_status in active:
            execution["status"] = "running"
            execution["error"] = ""
        else:
            execution["status"] = "failed"
            execution["error"] = str(child.get("error", "") or child_status)[:1000]
        execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
        _save_execution(execution)
        log_event(
            "orchestration.execution.reconciled",
            execution_id=resolved_id,
            child_kind=kind,
            child_status=child_status,
            wrapper_status=execution["status"],
        )
        return execution


def resume_orchestration_execution(execution_id: str) -> dict[str, object]:
    resolved_id = str(load_orchestration_execution(execution_id)["execution_id"])
    with operation_lock("orchestration", resolved_id):
        return _resume_orchestration_execution_unlocked(resolved_id)


def _resume_orchestration_execution_unlocked(execution_id: str) -> dict[str, object]:
    execution = load_orchestration_execution(execution_id)
    status = str(execution.get("status", ""))
    if status == "completed":
        return {"execution": execution, "result": None}
    if status == "abandoned":
        raise RuntimeError("orchestration execution is terminal: abandoned")
    if status not in {"running", "failed"}:
        raise ValueError(f"orchestration execution cannot be resumed from status: {status}")
    plan = _load_execution_plan(execution)
    task = str(plan["task"])
    stage = str(execution.get("stage", ""))
    roles = execution.get("roles", [])
    options = execution.get("options", {})
    link = execution.get("linked_session", {})
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ValueError("orchestration execution roles are invalid")
    if not isinstance(options, dict) or not isinstance(link, dict):
        raise ValueError("orchestration execution options or child link is invalid")
    child_kind = str(link.get("kind", ""))
    child_id = str(link.get("id", ""))
    if not child_id:
        raise ValueError("orchestration execution child session id is missing")
    exists = _child_checkpoint_exists(child_kind, child_id)
    execution["status"] = "running"
    execution["error"] = ""
    execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    _save_execution(execution)
    try:
        if stage == "planning":
            result: object = resume_sequence(child_id) if exists else run_sequence(
                roles,
                task,
                system=PLANNING_SYSTEM,
                retries=int(options.get("retries", 1)),
                run_id=child_id,
            )
        elif stage == "debate":
            result = resume_debate_rounds(child_id) if exists else run_debate_rounds(
                task,
                roles=roles,
                rounds=int(options.get("rounds", 2)),
                retries=int(options.get("retries", 1)),
                session_id=child_id,
            )
        elif stage == "repair":
            result = resume_repair_loop(child_id, retries=int(options.get("retries", 1))) if exists else run_repair_loop(
                task,
                max_attempts=options.get("max_attempts"),
                retries=int(options.get("retries", 1)),
                session_id=child_id,
            )
        else:
            raise ValueError(f"unknown orchestration execution stage: {stage}")
    except Exception as exc:
        execution["status"] = "failed"
        execution["error"] = str(exc)[:1000]
        execution["linked_session"] = {"kind": child_kind, "id": child_id, "status": "failed"}
        execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
        _save_execution(execution)
        log_event("orchestration.execution.resume.failed", execution_id=execution_id, error=str(exc))
        raise
    _apply_result_status(execution, stage, result, child_id)
    execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    _save_execution(execution)
    log_event(
        "orchestration.execution.resume.completed" if execution["status"] == "completed" else "orchestration.execution.resume.incomplete",
        execution_id=execution_id,
        stage=stage,
        child_status=execution["linked_session"]["status"],
    )
    return {"execution": execution, "result": result}


def _result_link(stage: str, result: object, fallback_id: str) -> dict[str, object]:
    if stage == "planning" and isinstance(result, list) and result and isinstance(result[0], dict):
        returned_id = str(result[0].get("run_id", ""))
        if returned_id and returned_id != fallback_id:
            raise ValueError("pipeline result id does not match the reserved child id")
        return {"kind": "pipeline", "id": fallback_id, "status": "completed"}
    if isinstance(result, dict):
        returned_id = str(result.get("session_id", ""))
        if returned_id and returned_id != fallback_id:
            raise ValueError(f"{stage} result id does not match the reserved child id")
        return {
            "kind": "debate" if stage == "debate" else "repair",
            "id": fallback_id,
            "status": result.get("status", "completed" if stage == "debate" else "unknown"),
        }
    return {"kind": "pipeline" if stage == "planning" else stage, "id": fallback_id, "status": "completed"}


def _apply_result_status(
    execution: dict[str, object], stage: str, result: object, fallback_id: str
) -> None:
    link = _result_link(stage, result, fallback_id)
    child_status = str(link.get("status", "unknown"))
    successful = (
        stage == "planning"
        or (stage == "debate" and child_status == "completed")
        or (stage == "repair" and child_status in {"approved", "already_verified"})
    )
    execution["linked_session"] = link
    execution["status"] = "completed" if successful else "failed"
    execution["error"] = "" if successful else f"linked {link['kind']} session ended with status: {child_status}"


def _stage_roles(plan: dict[str, object], stage: str) -> list[str]:
    if stage in {"planning", "debate"}:
        roles = plan.get("planning_roles", [])
    else:
        recommended = plan.get("recommended_roles", [])
        roles = [role for role in recommended if role in {"debugger", "coder", "reviewer"}]
    normalized = [str(role) for role in roles] if isinstance(roles, list) else []
    return [role for role in normalized if stage != "debate" or role != "decision_maker"]


def _enforce_stage_ready(plan: dict[str, object], stage: str, roles: list[str]) -> None:
    if not roles:
        raise ValueError(f"orchestration stage has no recommended roles: {stage}")
    role_set = set(roles)
    blocked = [
        item
        for item in plan.get("blocked_roles", [])
        if isinstance(item, dict) and str(item.get("role", "")) in role_set
    ]
    if blocked:
        details = "; ".join(
            f"{item.get('role')}: {', '.join(str(reason) for reason in item.get('blockers', []))}"
            for item in blocked
        )
        raise ValueError(f"orchestration stage is blocked: {details}")


def execute_task(
    task: str,
    *,
    stage: str = "planning",
    rounds: int = 2,
    retries: int = 1,
    max_attempts: int | None = None,
) -> dict[str, object]:
    if stage not in {"planning", "debate", "repair"}:
        raise ValueError("orchestration stage must be planning, debate, or repair")
    _validate_execution_options(
        {"rounds": rounds, "retries": retries, "max_attempts": max_attempts}
    )
    effective_rounds = rounds
    if stage == "debate":
        policy = load_orchestration_policy()
        effective_rounds = min(rounds, int(policy["max_debate_rounds"]))
    plan = build_role_plan(task)
    roles = _stage_roles(plan, stage)
    _enforce_stage_ready(plan, stage, roles)
    task_hash = hashlib.sha256(task.strip().encode("utf-8")).hexdigest()
    execution_stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    execution_id = "orchestration-" + execution_stamp
    child_kind = "pipeline" if stage == "planning" else stage
    child_id = f"pipeline-{execution_stamp}-{task_hash[:10]}" if stage == "planning" else execution_stamp
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    execution: dict[str, object] = {
        "format_version": 2,
        "execution_id": execution_id,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "task_sha256": task_hash,
        "stage": stage,
        "roles": roles,
        "options": {"rounds": effective_rounds, "retries": retries, "max_attempts": max_attempts},
        "status": "running",
        "linked_session": {"kind": child_kind, "id": child_id, "status": "reserved"},
        "error": "",
        "created_at": created_at,
        "updated_at": created_at,
    }
    _save_execution(execution)
    log_event("orchestration.execution.started", execution_id=execution_id, stage=stage, roles=roles, task_sha256=task_hash)
    try:
        if stage == "planning":
            result: object = run_sequence(
                roles,
                task,
                system="Produce an evidence-aware implementation plan with decisions, risks, and verification needs.",
                retries=retries,
                run_id=child_id,
            )
        elif stage == "debate":
            result = run_debate_rounds(
                task, roles=roles, rounds=effective_rounds, retries=retries, session_id=child_id
            )
        else:
            if "coder" not in roles or "reviewer" not in roles:
                raise ValueError("repair orchestration requires an implementation or bugfix task")
            result = run_repair_loop(
                task, max_attempts=max_attempts, retries=retries, session_id=child_id
            )
        _apply_result_status(execution, stage, result, child_id)
    except Exception as exc:
        execution["status"] = "failed"
        execution["error"] = str(exc)[:1000]
        execution["linked_session"] = {"kind": child_kind, "id": child_id, "status": "failed"}
        execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
        _save_execution(execution)
        log_event("orchestration.execution.failed", execution_id=execution_id, stage=stage, error=str(exc))
        raise
    execution["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    _save_execution(execution)
    log_event(
        "orchestration.execution.completed" if execution["status"] == "completed" else "orchestration.execution.incomplete",
        execution_id=execution_id,
        stage=stage,
        roles=roles,
        task_sha256=task_hash,
        child_status=execution["linked_session"]["status"],
    )
    return {
        "execution_id": execution_id,
        "status": execution["status"],
        "stage": stage,
        "task_tags": plan["task_tags"],
        "roles": roles,
        "plan_created_at": plan["created_at"],
        "linked_session": execution["linked_session"],
        "result": result,
    }
