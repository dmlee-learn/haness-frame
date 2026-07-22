from __future__ import annotations

import datetime as dt
import json

from .storage import load_json_object, update_json_object, write_text

SCORECARD = "workspace/scorecard.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_scorecard() -> dict[str, object]:
    return load_json_object(SCORECARD)


def scorecard_check() -> dict[str, object]:
    try:
        scorecard = load_scorecard()
    except ValueError as exc:
        return {"valid": False, "status": "invalid", "issues": [str(exc)], "check_count": 0}
    issues: list[str] = []
    checks = scorecard.get("checks", {})
    details = scorecard.get("details", {})
    if not isinstance(checks, dict):
        issues.append("workspace/scorecard.json checks must be a JSON object")
        checks = {}
    else:
        invalid_checks = sorted(str(name) for name, passed in checks.items() if not isinstance(passed, bool))
        if invalid_checks:
            issues.append("workspace/scorecard.json checks must contain boolean values: " + ", ".join(invalid_checks))
    if not isinstance(details, dict):
        issues.append("workspace/scorecard.json details must be a JSON object")
    return {
        "valid": not issues,
        "status": "valid" if not issues else "invalid",
        "issues": issues,
        "check_count": len(checks),
    }


def save_scorecard(scorecard: dict[str, object]) -> dict[str, object]:
    scorecard["last_updated_at"] = _now()
    write_text(SCORECARD, json.dumps(scorecard, indent=2, ensure_ascii=False))
    return scorecard


def mark_check(name: str, passed: bool, detail: str = "") -> dict[str, object]:
    def mutate(scorecard: dict[str, object]) -> None:
        checks = scorecard.setdefault("checks", {})
        if not isinstance(checks, dict):
            checks = {}
            scorecard["checks"] = checks
        checks[name] = bool(passed)
        details = scorecard.setdefault("details", {})
        if isinstance(details, dict) and detail:
            details[name] = detail
        scorecard["last_updated_at"] = _now()

    return update_json_object(SCORECARD, mutate)


def update_runtime_scorecard(
    *,
    status_ok: bool,
    next_ok: bool,
    evidence_ok: bool,
    decision_gate_allowed: bool,
    missing_docs: list[str],
    gate_issues: list[str],
) -> dict[str, object]:
    def mutate(scorecard: dict[str, object]) -> None:
        checks = scorecard.setdefault("checks", {})
        if not isinstance(checks, dict):
            checks = {}
            scorecard["checks"] = checks
        checks["status"] = status_ok
        checks["next"] = next_ok
        checks["evidence"] = evidence_ok
        checks["decision_gate"] = decision_gate_allowed
        scorecard["status"] = "ready_for_implementation" if decision_gate_allowed else "in_progress"
        scorecard["open_issues"] = list(missing_docs) + list(gate_issues)
        scorecard["last_updated_at"] = _now()

    return update_json_object(SCORECARD, mutate)


def scorecard_report() -> str:
    scorecard = load_scorecard()
    return json.dumps(scorecard, indent=2, ensure_ascii=False)
