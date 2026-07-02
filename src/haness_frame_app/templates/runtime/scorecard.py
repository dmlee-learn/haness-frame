from __future__ import annotations

import datetime as dt
import json

from .storage import read_text, write_text

SCORECARD = "workspace/scorecard.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_scorecard() -> dict[str, object]:
    payload = read_text(SCORECARD, "{}")
    try:
        scorecard = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return scorecard if isinstance(scorecard, dict) else {}


def save_scorecard(scorecard: dict[str, object]) -> dict[str, object]:
    scorecard["last_updated_at"] = _now()
    write_text(SCORECARD, json.dumps(scorecard, indent=2, ensure_ascii=False))
    return scorecard


def mark_check(name: str, passed: bool, detail: str = "") -> dict[str, object]:
    scorecard = load_scorecard()
    checks = scorecard.setdefault("checks", {})
    if not isinstance(checks, dict):
        checks = {}
        scorecard["checks"] = checks
    checks[name] = bool(passed)
    details = scorecard.setdefault("details", {})
    if isinstance(details, dict) and detail:
        details[name] = detail
    return save_scorecard(scorecard)


def update_runtime_scorecard(
    *,
    status_ok: bool,
    next_ok: bool,
    evidence_ok: bool,
    decision_gate_allowed: bool,
    missing_docs: list[str],
    gate_issues: list[str],
) -> dict[str, object]:
    scorecard = load_scorecard()
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
    return save_scorecard(scorecard)


def scorecard_report() -> str:
    scorecard = load_scorecard()
    return json.dumps(scorecard, indent=2, ensure_ascii=False)
