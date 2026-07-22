from __future__ import annotations

import compileall
import contextlib
import datetime as dt
import io
import json

from .audit import audit_check, log_event
from .diagnostics import check_services
from .debate import DEBATE_ROOT, LATEST_DEBATE_SESSION, judge_provenance_sha256, load_debate_session
from .engine import decision_gate
from .evidence import evidence_policy_report
from .manifest import validate_manifest
from .orchestration_policy import load_orchestration_policy
from .patching import load_repair_policy
from .repair import REPAIR_ROOT, load_repair_session, review_provenance_sha256
from .scorecard import mark_check, scorecard_check
from .session_overview import session_overview
from .services import debate_judge_independence, review_independence, service_execution_identity
from .storage import ROOT, write_text
from .verification import run_verification_commands
from .workflow import LATEST_SESSION, RUN_ROOT, load_pipeline_session


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _collect_issues(report: dict[str, object]) -> list[str]:
    issues: list[str] = []
    manifest = report["manifest"]
    evidence = report["evidence"]
    gate = report["decision_gate"]
    services = report["services"]
    orchestration = report["orchestration"]
    debate = report["debate"]
    repair = report["repair"]
    executions = report["execution_history"]
    audit = report["audit"]
    scorecard = report["scorecard"]
    if not report["compileall"]:
        issues.append("source compilation failed")
    if not audit.get("valid"):
        audit_issues = audit.get("issues", [])
        if audit_issues:
            issues.extend(f"audit: {item}" for item in audit_issues)
        else:
            issues.append("audit log validation failed")
    if not scorecard.get("valid"):
        scorecard_issues = scorecard.get("issues", [])
        if scorecard_issues:
            issues.extend(f"scorecard: {item}" for item in scorecard_issues)
        else:
            issues.append("scorecard validation failed")
    if not manifest.get("valid") and not manifest.get("issues"):
        issues.append("manifest validation failed")
    issues.extend(f"manifest: {item}" for item in manifest.get("issues", []))
    if not evidence.get("valid") and not evidence.get("issues"):
        issues.append("evidence validation failed")
    evidence_issue_list = [str(item) for item in evidence.get("issues", [])]
    evidence_issues = set(evidence_issue_list)
    issues.extend(f"evidence: {item}" for item in evidence_issue_list)
    if not gate.get("allowed") and not gate.get("issues"):
        issues.append("decision gate is closed")
    issues.extend(f"decision: {item}" for item in gate.get("issues", []) if str(item) not in evidence_issues)
    configuration_issues = services.get("configuration_issues", [])
    if isinstance(configuration_issues, list):
        issues.extend(f"service: {item}" for item in configuration_issues)
        service_issue_count = len(configuration_issues)
    else:
        service_issue_count = 0
    service_issue_count += len(services.get("unassigned_roles", []))
    for role in services.get("unassigned_roles", []):
        issues.append(f"service: role is unassigned: {role}")
    for service in services.get("services", []):
        name = service.get("name") or service.get("base_url") or "unnamed"
        service_issue_count += len(service.get("issues", []))
        issues.extend(f"service {name}: {item}" for item in service.get("issues", []))
    if not services.get("valid") and not service_issue_count:
        issues.append("service validation failed")
    if not orchestration.get("valid"):
        orchestration_issues = orchestration.get("issues", [])
        if orchestration_issues:
            issues.extend(f"orchestration: {item}" for item in orchestration_issues)
        else:
            issues.append("orchestration validation failed")
    if not debate.get("valid"):
        debate_issues = debate.get("issues", [])
        if debate_issues:
            issues.extend(f"debate: {item}" for item in debate_issues)
        else:
            issues.append("debate validation failed")
    if not repair.get("valid"):
        repair_issues = repair.get("issues", [])
        if repair_issues:
            issues.extend(f"repair: {item}" for item in repair_issues)
        else:
            issues.append("repair validation failed")
    if not executions.get("valid"):
        execution_issues = executions.get("issues", [])
        if execution_issues:
            issues.extend(f"execution history: {item}" for item in execution_issues)
        else:
            issues.append("execution history validation failed")
    verification = report.get("verification")
    if isinstance(verification, dict) and not verification.get("passed") and not verification.get("skipped"):
        issues.append("verification commands failed")
    return list(dict.fromkeys(issues))


def _collect_warnings(report: dict[str, object]) -> list[str]:
    services = report.get("services", {})
    if not isinstance(services, dict):
        return []
    warnings = services.get("warnings", [])
    return [f"service: {item}" for item in warnings] if isinstance(warnings, list) else []


def _has_session_checkpoint(latest: str, root: str) -> bool:
    if (ROOT / latest).is_file():
        return True
    session_root = ROOT / root
    return session_root.is_dir() and any(session_root.glob("*/session.json"))


def orchestration_health_report() -> dict[str, object]:
    try:
        policy = load_orchestration_policy()
    except ValueError as exc:
        return {"valid": False, "status": "invalid_policy", "issues": [str(exc)]}
    if not _has_session_checkpoint(LATEST_SESSION, RUN_ROOT):
        return {"valid": True, "status": "not_started", "issues": [], "policy": policy}
    try:
        session = load_pipeline_session("latest")
    except ValueError as exc:
        return {"valid": False, "status": "invalid_checkpoint", "issues": [str(exc)], "policy": policy}
    status = str(session.get("status", "unknown"))
    valid = status in {"completed", "abandoned"}
    issues = [] if valid else [f"latest pipeline is {status}: {session.get('error', '')}".rstrip(": ")]
    roles = session.get("roles", [])
    results = session.get("results", [])
    return {
        "valid": valid,
        "status": status,
        "issues": issues,
        "run_id": session.get("run_id", ""),
        "completed_roles": len(results) if isinstance(results, list) else 0,
        "total_roles": len(roles) if isinstance(roles, list) else 0,
        "budget": session.get("budget", {}),
        "policy": policy,
    }


def debate_health_report() -> dict[str, object]:
    try:
        policy = load_orchestration_policy()
    except ValueError as exc:
        return {"valid": False, "status": "invalid_policy", "issues": [str(exc)]}
    strict = bool(policy.get("require_independent_debate_judge_service", False))
    if not _has_session_checkpoint(LATEST_DEBATE_SESSION, DEBATE_ROOT):
        configured = debate_judge_independence()
        configuration_issues = []
        if strict and (not configured.get("assessed") or not configured.get("independent_service")):
            configuration_issues.append(
                f"independent debate judge service is required: {configured.get('reason', 'not assessed')}"
            )
        return {
            "valid": not configuration_issues,
            "status": "configuration_blocked" if configuration_issues else "not_started",
            "issues": configuration_issues,
            "policy": policy,
            "configured_judge_independence": configured,
        }
    try:
        session = load_debate_session("latest")
    except ValueError as exc:
        return {"valid": False, "status": "invalid_checkpoint", "issues": [str(exc)]}
    roles = session.get("roles", [])
    selected_roles = [str(role) for role in roles] if isinstance(roles, list) else []
    configured = debate_judge_independence(selected_roles)
    configuration_issues = []
    if strict and (not configured.get("assessed") or not configured.get("independent_service")):
        configuration_issues.append(
            f"independent debate judge service is required: {configured.get('reason', 'not assessed')}"
        )
    status = str(session.get("status", "unknown"))
    issues = list(configuration_issues)
    if status not in {"completed", "abandoned"}:
        issues.append(f"latest debate is {status}: {session.get('error', '')}".rstrip(": "))
    result = session.get("result", {})
    if strict and status == "completed":
        actual = result.get("actual_judge_independence", {}) if isinstance(result, dict) else {}
        if not isinstance(actual, dict) or not actual.get("assessed") or not actual.get("independent_service"):
            issues.append("completed debate lacks independent actual judge evidence")
        stored = str(result.get("judge_provenance_sha256", "")) if isinstance(result, dict) else ""
        if not stored:
            issues.append("completed debate lacks judge provenance hash")
        elif stored != judge_provenance_sha256(result):
            issues.append("completed debate judge provenance hash mismatch")
    valid = status in {"completed", "abandoned"} and not issues
    results = session.get("round_results", [])
    return {
        "valid": valid,
        "status": status,
        "issues": issues,
        "session_id": session.get("session_id", ""),
        "stage": session.get("stage", ""),
        "completed_rounds": len(results) if isinstance(results, list) else 0,
        "requested_rounds": session.get("rounds_requested", 0),
        "policy": policy,
        "configured_judge_independence": configured,
        "actual_judge_independence": result.get("actual_judge_independence", {}) if isinstance(result, dict) else {},
    }


def repair_health_report() -> dict[str, object]:
    try:
        policy = load_repair_policy()
    except ValueError as exc:
        return {"valid": False, "status": "invalid_policy", "issues": [str(exc)]}
    independence = review_independence()
    strict = bool(policy.get("require_independent_reviewer_service", False))
    policy_issues = []
    if strict and not independence.get("assessed"):
        policy_issues.append(f"independent reviewer service is required: {independence.get('reason', 'not assessed')}")
    elif strict and not independence.get("independent_service"):
        policy_issues.append("independent reviewer service is required: coder and reviewer share provider endpoint and model")
    latest = f"{REPAIR_ROOT}/latest.json"
    if not _has_session_checkpoint(latest, REPAIR_ROOT):
        return {
            "valid": not policy_issues,
            "status": "configuration_blocked" if policy_issues else "not_started",
            "issues": policy_issues,
            "policy": policy,
            "review_independence": independence,
        }
    try:
        session = load_repair_session("latest")
    except ValueError as exc:
        return {"valid": False, "status": "invalid_checkpoint", "issues": [str(exc)]}
    status = str(session.get("status", "unknown"))
    actual_review: dict[str, object] = {"assessed": False, "independent_service": None, "reason": "not required"}
    if strict and status == "approved":
        attempts = session.get("attempts", [])
        approved = next(
            (
                item for item in reversed(attempts)
                if isinstance(item, dict) and item.get("status") == "approved"
            ),
            None,
        ) if isinstance(attempts, list) else None
        coder = approved.get("coder_service", {}) if isinstance(approved, dict) else {}
        reviewer = approved.get("reviewer_service", {}) if isinstance(approved, dict) else {}
        coder_identity = service_execution_identity(coder) if isinstance(coder, dict) else ("", "", "")
        reviewer_identity = service_execution_identity(reviewer) if isinstance(reviewer, dict) else ("", "", "")
        if not all(coder_identity) or not all(reviewer_identity):
            actual_review = {
                "assessed": False,
                "independent_service": None,
                "reason": "approved repair lacks complete actual coder/reviewer service identities",
            }
            policy_issues.append(str(actual_review["reason"]))
        else:
            independent_actual = coder_identity != reviewer_identity
            actual_review = {
                "assessed": True,
                "independent_service": independent_actual,
                "reason": "distinct actual invocation identities" if independent_actual else "shared actual invocation identity",
            }
            if not independent_actual:
                policy_issues.append("approved repair used the same actual coder/reviewer service identity")
        if isinstance(approved, dict):
            stored_provenance = str(approved.get("review_provenance_sha256", ""))
            expected_provenance = review_provenance_sha256(approved)
            if not stored_provenance:
                policy_issues.append("approved repair lacks review provenance hash")
            elif stored_provenance != expected_provenance:
                policy_issues.append("approved repair review provenance hash mismatch")
    valid = status in {"approved", "already_verified", "abandoned", "superseded"} and not policy_issues
    issues = list(policy_issues)
    if status not in {"approved", "already_verified", "abandoned", "superseded"}:
        issues.append(f"latest repair is {status}: {session.get('error', '')}".rstrip(": "))
    attempts = session.get("attempts", [])
    return {
        "valid": valid,
        "status": status,
        "issues": issues,
        "session_id": session.get("session_id", ""),
        "attempts": len(attempts) if isinstance(attempts, list) else 0,
        "budget": session.get("budget", {}),
        "policy": policy,
        "review_independence": independence,
        "actual_review_independence": actual_review,
    }


def execution_history_health_report() -> dict[str, object]:
    overview = session_overview(limit=10, unresolved_only=True)
    attention = int(overview["needs_attention"])
    issues = [
        f"{item.get('kind')} {item.get('id')} is {item.get('status')}"
        for item in overview["sessions"]
    ]
    if attention > len(issues):
        issues.append(f"{attention - len(issues)} additional unresolved session(s)")
    if issues:
        issues.append("Run `python app.py runs --unresolved` and resolve or abandon each session.")
    return {
        "valid": attention == 0,
        "status": "resolved" if attention == 0 else "unresolved",
        "issues": issues,
        "total_sessions": overview["total_sessions"],
        "needs_attention": attention,
        "sessions": overview["sessions"],
    }


def qualification_report(
    *,
    probe_services: bool = False,
    run_verification: bool = False,
    service_timeout: float = 2.0,
) -> dict[str, object]:
    started_at = _now()
    compile_output = io.StringIO()
    with contextlib.redirect_stdout(compile_output), contextlib.redirect_stderr(compile_output):
        compile_ok = compileall.compile_dir(str(ROOT / "src"), quiet=1)
    report: dict[str, object] = {
        "started_at": started_at,
        "completed_at": "",
        "probe_services": probe_services,
        "verification_requested": run_verification,
        "compileall": compile_ok,
        "compile_output": compile_output.getvalue()[-12000:],
        "audit": audit_check(),
        "scorecard": scorecard_check(),
        "manifest": validate_manifest(),
        "services": check_services(probe=probe_services, timeout=service_timeout),
        "evidence": evidence_policy_report(),
        "decision_gate": decision_gate(),
        "orchestration": orchestration_health_report(),
        "debate": debate_health_report(),
        "repair": repair_health_report(),
        "execution_history": execution_history_health_report(),
    }
    gate_allowed = bool(report["decision_gate"].get("allowed"))
    if run_verification and gate_allowed:
        report["verification"] = run_verification_commands()
    elif run_verification:
        report["verification"] = {"passed": False, "skipped": True, "reason": "decision gate is closed"}
    else:
        report["verification"] = {"passed": None, "skipped": True, "reason": "not requested"}
    issues = _collect_issues(report)
    warnings = _collect_warnings(report)
    ready = not issues
    qualified = ready and run_verification and bool(report["verification"].get("passed"))
    report["issues"] = issues
    report["warnings"] = warnings
    report["ready"] = ready
    report["qualified"] = qualified
    report["status"] = "qualified" if qualified else ("ready" if ready else "blocked")
    if issues:
        report["next_actions"] = issues[:10]
    elif qualified:
        report["next_actions"] = warnings[:10]
    else:
        report["next_actions"] = [
            "Run `python app.py qualify --run-verification` to execute approved tests.",
            *warnings[:9],
        ]
    report["completed_at"] = _now()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_text(f"workspace/qualifications/{stamp}.json", json.dumps(report, indent=2, ensure_ascii=False))
    write_text("workspace/qualifications/latest.json", json.dumps(report, indent=2, ensure_ascii=False))
    if report["scorecard"].get("valid"):
        mark_check("qualification", qualified, str(report["status"]))
    log_event(
        "qualification.completed",
        qualified=report["qualified"],
        issues=len(issues),
        verification_requested=run_verification,
        probe_services=probe_services,
    )
    return report


def print_qualification(**kwargs: object) -> int:
    report = qualification_report(**kwargs)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 1
