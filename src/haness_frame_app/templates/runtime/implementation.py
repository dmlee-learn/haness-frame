from __future__ import annotations

from pathlib import Path, PurePosixPath

from .ai_cache import invoke_cached
from .engine import decision_gate, enforce_decision_gate
from .finish import finish_project
from .patching import apply_patch_text, patch_plan_report, rollback_patch
from .repair import extract_unified_diff, load_repair_policy, normalize_unified_diff_hunks
from .snapshots import create_snapshot
from .storage import ROOT, read_text, write_text
from .verification import verification_plan


def _project_inventory(policy: dict[str, object], limit: int = 100) -> str:
    roots = policy.get("editable_roots", [])
    if not isinstance(roots, list):
        return "(unavailable)"
    paths: list[str] = []
    for root_text in roots:
        root = PurePosixPath(str(root_text).replace("\\", "/"))
        target = ROOT / Path(*root.parts)
        if not target.is_dir():
            continue
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            paths.append(path.relative_to(ROOT).as_posix())
            if len(paths) >= limit:
                break
        if len(paths) >= limit:
            break
    return "\n".join(f"- {path}" for path in paths) or "(no implementation files yet)"


def _coder_prompt(task: str, decision: str, inventory: str) -> str:
    return f"""Implement the accepted project task.
Return exactly one UTF-8 unified diff in a ```diff fenced block and no prose.
You may create new files or modify existing files only under src/, tests/, or implementation/.
Use accurate unified-diff hunk locations and include tests for success and failure behavior.
Do not modify the harness runtime, workspace policy, evidence, or decision documents.

Task:
{task}

Accepted decision and verification contract:
{decision[-12000:]}

Current editable files:
{inventory}
"""


def implement_project(
    task: str,
    *,
    max_tokens: int | None = None,
    retries: int = 0,
    label: str = "implementation",
) -> dict[str, object]:
    task = task.strip()
    if not task:
        raise ValueError("implementation task must be a non-empty string")
    enforce_decision_gate("coder")
    plan = verification_plan()
    if not plan.get("approved"):
        return {
            "status": "blocked",
            "stage": "verification_plan",
            "verification_plan": plan,
            "next_action": "Approve the decision verification commands before implementation.",
        }

    policy = load_repair_policy()
    configured_tokens = int(policy.get("ai_max_tokens", 4096))
    token_limit = configured_tokens if max_tokens is None else max(128, min(max_tokens, configured_tokens))
    decision = read_text("docs/03-decision-record.md", "")
    result = invoke_cached(
        "coder",
        _coder_prompt(task, decision, _project_inventory(policy)),
        max_tokens=token_limit,
        retries=retries,
    )
    diff = normalize_unified_diff_hunks(extract_unified_diff(str(result.get("content", ""))))
    candidate_path = write_text("workspace/candidate.diff", diff)
    candidate = patch_plan_report(diff)
    snapshot = create_snapshot(label)
    patch = apply_patch_text(diff)
    finish = finish_project(label=label)
    report: dict[str, object] = {
        "status": "completed" if finish.get("status") == "completed" else "rolled_back",
        "stage": "completed" if finish.get("status") == "completed" else "finish",
        "candidate_diff": str(candidate_path),
        "candidate": candidate,
        "snapshot": snapshot,
        "patch": patch,
        "finish": finish,
        "gate": decision_gate(),
    }
    if report["status"] != "completed":
        report["rollback"] = rollback_patch(str(patch["patch_id"]))
        report["next_action"] = "Review finish errors and rerun implementation with a corrected task."
    return report
