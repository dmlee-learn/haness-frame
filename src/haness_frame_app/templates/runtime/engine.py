from __future__ import annotations

import datetime as dt
from pathlib import Path

from .evidence import decision_references_evidence, evidence_gap_counts, evidence_status, evidence_summary, load_evidence
from .roles import ROLE_ORDER, describe_role
from .scorecard import mark_check, update_runtime_scorecard
from .storage import ROOT, STATE_FILE, ensure_workspace, load_state, read_text, save_state, write_text

REQUIRED_DOCS = [
    "context/business-context.md",
    "context/source-materials.md",
    "research/search-backlog.md",
    "docs/01-project-discovery.md",
    "docs/02-role-discussion.md",
    "docs/03-decision-record.md",
]

GATED_ROLES = {"coder", "reviewer"}


def _section_text(text: str, heading: str) -> str:
    marker = f"## {heading}"
    parts = text.split(marker, 1)
    if len(parts) != 2:
        return ""
    tail = parts[1]
    next_heading = tail.find("\n## ")
    if next_heading != -1:
        tail = tail[:next_heading]
    return tail.strip()


def bootstrap() -> dict[str, object]:
    ensure_workspace()
    state = load_state()
    if not state:
        state = {
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "status": "bootstrap",
            "current_stage": "context",
            "notes": [],
            "role_assignments": {},
        }
        save_state(state)
    return state


def missing_docs() -> list[str]:
    missing = []
    for rel_path in REQUIRED_DOCS:
        if not (ROOT / rel_path).exists():
            missing.append(rel_path)
    return missing


def next_action() -> str:
    missing = missing_docs()
    if missing:
        return f"Complete: {missing[0]}"
    ok, issues = evidence_status()
    if not ok:
        if (ROOT / "workspace" / "evidence" / "search-plan.json").exists():
            return "Review `research/search-evidence-gaps.md` and `research/search-evidence-draft.md`, then capture at least one structured evidence record."
        return f"Capture search evidence: {issues[0]}"
    gate = decision_gate()
    if gate["allowed"]:
        return "Decision approved. Move to implementation."
    return "Draft the decision record with `python app.py decision-draft`, then resolve the remaining gate issues."


def decision_gate() -> dict[str, object]:
    decision_text = read_text("docs/03-decision-record.md", "")
    issues: list[str] = []
    evidence_ok, evidence_issues = evidence_status()
    issues.extend(evidence_issues)
    accepted = _section_text(decision_text, "Accepted Decision")
    brief = _section_text(decision_text, "Implementation Brief For Coder")
    verification = _section_text(decision_text, "Verification Commands")
    if not accepted:
        issues.append("Accepted Decision is required")
    if not brief:
        issues.append("Implementation Brief For Coder is required")
    if not verification:
        issues.append("Verification Commands are required")
    if not decision_references_evidence():
        issues.append("Decision Record must cite or summarize evidence")
    gate = {
        "allowed": not issues,
        "issues": issues,
        "accepted_decision": accepted,
        "implementation_brief": brief,
        "verification_commands": verification,
    }
    mark_check("decision_gate", bool(gate["allowed"]), "; ".join(issues[:3]))
    return gate


def enforce_decision_gate(role: str) -> None:
    if role not in GATED_ROLES:
        return
    gate = decision_gate()
    if gate["allowed"]:
        return
    issue_text = "\n".join(f"- {issue}" for issue in gate["issues"])
    raise RuntimeError(f"decision gate blocks role '{role}' until resolved:\n{issue_text}")


def refresh_runtime_scorecard(gate: dict[str, object] | None = None) -> dict[str, object]:
    missing = missing_docs()
    evidence_ok, _ = evidence_status()
    gate = gate or decision_gate()
    return update_runtime_scorecard(
        status_ok=True,
        next_ok=not missing and evidence_ok,
        evidence_ok=evidence_ok,
        decision_gate_allowed=bool(gate["allowed"]),
        missing_docs=missing,
        gate_issues=list(gate["issues"]),
    )


def status_report() -> str:
    state = bootstrap()
    lines = [
        "# Harness Status",
        "",
        f"Status: {state.get('status', 'unknown')}",
        f"Stage: {state.get('current_stage', 'unknown')}",
        f"Next action: {next_action()}",
        "",
        "Missing documents:",
    ]
    missing = missing_docs()
    gate = decision_gate()
    refresh_runtime_scorecard(gate)
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- none")
    lines.extend(["", "Decision gate:", f"- allowed: {gate['allowed']}"])
    if gate["issues"]:
        lines.extend(f"- {issue}" for issue in gate["issues"])
    return "\n".join(lines)


def summary_report() -> str:
    state = bootstrap()
    missing = missing_docs()
    gate = decision_gate()
    evidence_records = load_evidence()
    gap_counts = evidence_gap_counts()
    lines = [
        "# Harness Summary",
        "",
        f"Status: {state.get('status', 'unknown')}",
        f"Stage: {state.get('current_stage', 'unknown')}",
        f"Next action: {next_action()}",
        "",
        f"Missing docs: {len(missing)}",
        f"Evidence records: {len(evidence_records)}",
        f"Planned searches: {gap_counts['planned']}",
        f"Covered searches: {gap_counts['covered']}",
        f"Evidence gaps: {gap_counts['missing']}",
        f"Decision gate: {gate['allowed']}",
    ]
    if missing:
        lines.extend(["", "Missing documents:"] + [f"- {item}" for item in missing])
    if gate["issues"]:
        lines.extend(["", "Gate issues:"] + [f"- {issue}" for issue in gate["issues"]])
    return "\n".join(lines)


def role_packet(role: str) -> str:
    state = bootstrap()
    working_description = state.get("working_description", "")
    assignment = state.get("role_assignments", {}).get(role, "")
    return f'''# Role Packet: {role}

Role summary:

{describe_role(role)}

Assigned service:

```text
{assignment}
```

Working description:

```text
{working_description}
```

Current action:

{next_action()}

Context files:

- context/business-context.md
- context/source-materials.md
- research/search-backlog.md
- research/search-evidence.md

Search evidence:

{evidence_summary()}

Decision gate:

- docs/03-decision-record.md
'''


def render_role_packets() -> list[Path]:
    state = bootstrap()
    outputs = []
    for role in ROLE_ORDER:
        path = write_text(f"workspace/packs/{role}.md", role_packet(role))
        outputs.append(path)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    save_state(state)
    mark_check("render", True, f"{len(outputs)} role packet(s)")
    return outputs
