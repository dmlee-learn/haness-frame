from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
TEMPLATE_RUNTIME = ROOT / "src" / "haness_frame_app" / "templates" / "runtime"
RUNTIME_FILES = [path.name for path in TEMPLATE_RUNTIME.glob("*.py")]
EXTRA_MANIFEST_FILES = [
    "workspace/evidence/search-plan.json",
    "workspace/evidence/claim-evidence.json",
    "workspace/evidence-policy.json",
    "research/search-evidence-draft.md",
    "research/search-evidence-gaps.md",
    "src/harness_app/decision.py",
    "src/harness_app/verification.py",
    "workspace/verification-policy.json",
    "src/harness_app/patching.py",
    "workspace/repair-policy.json",
    "workspace/orchestration-policy.json",
    "workspace/search-policy.json",
    "workspace/archive-policy.json",
    "src/harness_app/repair.py",
    "src/harness_app/finish.py",
    "src/harness_app/implementation.py",
    "src/harness_app/ai_cache.py",
    "src/harness_app/budget.py",
    "src/harness_app/qualification.py",
    "src/harness_app/network_safety.py",
    "src/harness_app/search_discovery.py",
    "src/harness_app/evidence_policy.py",
    "src/harness_app/claims.py",
    "src/harness_app/provenance.py",
    "src/harness_app/evidence_fetch.py",
    "src/harness_app/diagnostics.py",
    "src/harness_app/orchestration.py",
    "src/harness_app/orchestration_plan_validation.py",
    "src/harness_app/orchestration_recovery.py",
    "src/harness_app/orchestration_policy.py",
    "src/harness_app/session_overview.py",
]
COMMAND_SNIPPETS = [
    "python -m harness_app implement --task \"Implement the approved change\"",
    "python -m harness_app finish",
    "python -m harness_app qualify",
    "python -m harness_app live-check --role planner",
    "python -m harness_app summary",
    "python -m harness_app runs --unresolved",
    "python -m harness_app search-plan",
    "python -m harness_app search-discover",
    "python -m harness_app evidence-draft",
    "python -m harness_app evidence-check",
    "python -m harness_app claim-add --claim \"...\" --support-url URL",
    "python -m harness_app claim-check",
    "python -m harness_app claims",
    "python -m harness_app evidence-fetch --url URL --query QUERY --why-it-matters REASON --recommended-use USE",
    "python -m harness_app evidence-source-check --url URL",
    "python -m harness_app evidence-source-check-all",
    "python -m harness_app evidence-source-refresh --url URL",
    "python -m harness_app evidence-gaps",
    "python -m harness_app evidence-commit",
    "python -m harness_app decision-template",
    "python -m harness_app decision-draft",
    "python -m harness_app verify",
    "python -m harness_app verification-plan",
    "python -m harness_app verification-run",
    "python -m harness_app patch-plan --file workspace/candidate.diff",
    "python -m harness_app patch-apply --file workspace/candidate.diff",
    "python -m harness_app patch-rollback --id PATCH_ID",
    "python -m harness_app repair-run --task \"Fix the failing implementation\"",
    "python -m harness_app repair-status",
    "python -m harness_app repair-resume --id SESSION_ID",
    "python -m harness_app repair-abandon --id SESSION_ID --reason \"Superseded repair\"",
    "python -m harness_app debate-rounds --prompt \"Compare the implementation options\" --rounds 2",
    "python -m harness_app debate-status --id latest",
    "python -m harness_app debate-resume --id DEBATE_ID",
    "python -m harness_app archive-verify",
    "python -m harness_app audit-check",
    "python -m harness_app audit-export",
    "python -m harness_app ai-cache-status",
    "python -m harness_app ai-cache-prune --max-age-seconds 86400",
    "python -m harness_app invoke --role planner --prompt \"Summarize the project state\" --json",
    "python -m harness_app role-plan --task \"Describe the requested work\"",
    "python -m harness_app orchestrate --stage planning --task \"Describe the requested work\"",
    "python -m harness_app orchestrate-status --id latest",
    "python -m harness_app orchestrate-resume --id EXECUTION_ID",
    "python -m harness_app orchestrate-reconcile --id EXECUTION_ID",
    "python -m harness_app orchestrate-reconcile-all --limit 100",
    "python -m harness_app orchestrate-abandon --id EXECUTION_ID --reason \"Superseded orchestration\"",
    "python -m harness_app pipeline-status --id latest",
    "python -m harness_app pipeline-resume --id RUN_ID",
    "python -m harness_app pipeline-abandon --id RUN_ID --reason \"Superseded run\"",
]


def copy_runtime(project: Path) -> None:
    dst = project / "src" / "harness_app"
    dst.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copy2(TEMPLATE_RUNTIME / name, dst / name)


def update_manifest(project: Path) -> None:
    path = project / "workspace" / "manifest.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", [])
    if not isinstance(files, list):
        files = []
    for rel in EXTRA_MANIFEST_FILES:
        if rel not in files:
            files.append(rel)
    data["files"] = files
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def update_runtime_doc(project: Path) -> None:
    path = project / "docs" / "06-system-runtime.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    updated = text
    for snippet in COMMAND_SNIPPETS:
        if snippet not in updated:
            anchor = "python -m harness_app debate"
            if anchor in updated:
                updated = updated.replace(anchor, f"{snippet}\n{anchor}", 1)
            else:
                updated = updated.rstrip() + f"\n{snippet}\n"
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def ensure_new_files(project: Path) -> None:
    claims = project / "workspace" / "evidence" / "claim-evidence.json"
    if not claims.exists():
        claims.parent.mkdir(parents=True, exist_ok=True)
        claims.write_text("[]\n", encoding="utf-8")
    archive_policy = project / "workspace" / "archive-policy.json"
    if not archive_policy.exists():
        archive_policy.parent.mkdir(parents=True, exist_ok=True)
        archive_policy.write_text(
            json.dumps(
                {
                    "max_files": 10000,
                    "max_file_bytes": 50000000,
                    "max_total_bytes": 500000000,
                    "exclude_globs": [
                        ".git/*",
                        "workspace/archives/*",
                        "workspace/.locks/*",
                        "workspace/.operations/*",
                        "**/.*.tmp",
                        "__pycache__/*",
                        "**/__pycache__/*",
                        "*.pyc",
                        ".env",
                        "*.key",
                        "*.pem",
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    else:
        payload = json.loads(archive_policy.read_text(encoding="utf-8"))
        patterns = payload.setdefault("exclude_globs", [])
        for pattern in ("workspace/.locks/*", "workspace/.operations/*", "**/.*.tmp"):
            if pattern not in patterns:
                patterns.append(pattern)
        archive_policy.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    search_policy = project / "workspace" / "search-policy.json"
    if not search_policy.exists():
        search_policy.parent.mkdir(parents=True, exist_ok=True)
        search_policy.write_text(
            json.dumps(
                {
                    "enabled": False,
                    "provider": "searxng",
                    "base_url": "http://127.0.0.1:8888",
                    "allow_private_network": True,
                    "allowed_domains": [],
                    "max_queries_per_run": 8,
                    "max_results_per_query": 5,
                    "timeout_seconds": 15,
                    "max_response_bytes": 2000000,
                    "language": "all",
                    "categories": "general",
                    "safesearch": 1,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    evidence_policy = project / "workspace" / "evidence-policy.json"
    if not evidence_policy.exists():
        evidence_policy.parent.mkdir(parents=True, exist_ok=True)
        evidence_policy.write_text(
            json.dumps(
                {
                    "min_records": 2,
                    "min_distinct_urls": 2,
                    "allowed_confidence": ["high", "medium"],
                    "max_age_days": 3650,
                    "max_future_skew_minutes": 10,
                    "min_excerpt_chars": 20,
                    "min_search_coverage_ratio": 0.0,
                    "fetch_enabled": True,
                    "fetch_timeout_seconds": 10,
                    "fetch_max_bytes": 1000000,
                    "fetch_excerpt_chars": 1200,
                    "fetch_allowed_content_types": ["text/html", "text/plain", "application/json"],
                    "fetch_allowed_domains": [],
                    "allow_private_network": False,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    evidence_policy_data = json.loads(evidence_policy.read_text(encoding="utf-8"))
    fetch_defaults = {
        "fetch_enabled": True,
        "fetch_timeout_seconds": 10,
        "fetch_max_bytes": 1000000,
        "fetch_excerpt_chars": 1200,
        "fetch_allowed_content_types": ["text/html", "text/plain", "application/json"],
        "fetch_allowed_domains": [],
        "allow_private_network": False,
        "require_claim_matrix": False,
        "require_decision_snapshot": False,
        "min_claims": 1,
        "min_supporting_sources_per_claim": 1,
        "require_challenge_resolution": True,
        "allowed_claim_confidence": ["high", "medium"],
        "require_source_fingerprint": False,
        "require_source_revalidation": False,
        "max_source_verification_age_days": 30,
        "max_source_checks_per_run": 20,
    }
    if any(name not in evidence_policy_data for name in fetch_defaults):
        for name, value in fetch_defaults.items():
            evidence_policy_data.setdefault(name, value)
        evidence_policy.write_text(json.dumps(evidence_policy_data, indent=2, ensure_ascii=False), encoding="utf-8")
    repair_policy = project / "workspace" / "repair-policy.json"
    if not repair_policy.exists():
        repair_policy.parent.mkdir(parents=True, exist_ok=True)
        repair_policy.write_text(
            json.dumps(
                {
                    "editable_roots": ["src", "tests", "implementation"],
                    "max_patch_files": 20,
                    "max_patch_bytes": 200000,
                    "max_attempts": 3,
                    "rollback_on_failure": True,
                    "require_independent_reviewer_service": False,
                    "max_context_files": 8,
                    "max_context_chars": 40000,
                    "reuse_ai_responses": True,
                    "ai_cache_max_age_seconds": 86400,
                    "max_elapsed_seconds": 1800,
                    "max_ai_calls": 12,
                    "ai_max_tokens": 4096,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    repair_policy_data = json.loads(repair_policy.read_text(encoding="utf-8"))
    repair_budget_defaults = {
        "max_elapsed_seconds": 1800,
        "max_ai_calls": 12,
        "ai_max_tokens": 4096,
        "require_independent_reviewer_service": False,
    }
    if any(name not in repair_policy_data for name in repair_budget_defaults):
        for name, value in repair_budget_defaults.items():
            repair_policy_data.setdefault(name, value)
        repair_policy.write_text(json.dumps(repair_policy_data, indent=2, ensure_ascii=False), encoding="utf-8")
    orchestration_policy = project / "workspace" / "orchestration-policy.json"
    if not orchestration_policy.exists():
        orchestration_policy.parent.mkdir(parents=True, exist_ok=True)
        orchestration_policy.write_text(
            json.dumps(
                {
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
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    orchestration_policy_data = json.loads(orchestration_policy.read_text(encoding="utf-8"))
    orchestration_defaults = {
        "min_output_chars": 20,
        "max_output_chars": 100000,
        "max_debate_rounds": 5,
        "max_debate_elapsed_seconds": 3600,
        "max_debate_ai_calls": 32,
        "require_independent_debate_judge_service": False,
    }
    if any(name not in orchestration_policy_data for name in orchestration_defaults):
        for name, value in orchestration_defaults.items():
            orchestration_policy_data.setdefault(name, value)
        orchestration_policy.write_text(
            json.dumps(orchestration_policy_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    policy = project / "workspace" / "verification-policy.json"
    if not policy.exists():
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(
            json.dumps(
                {
                    "allowed_commands": [
                        "python -m compileall src",
                        "python app.py manifest",
                        "python app.py search-plan",
                        "python app.py verify",
                        "python app.py scorecard",
                    ],
                    "timeout_seconds": 120,
                    "max_output_chars": 12000,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    evidence_plan = project / "workspace" / "evidence" / "search-plan.json"
    if not evidence_plan.exists():
        evidence_plan.parent.mkdir(parents=True, exist_ok=True)
        evidence_plan.write_text(json.dumps({"provider": "google", "searches": []}, indent=2, ensure_ascii=False), encoding="utf-8")
    draft = project / "research" / "search-evidence-draft.md"
    if not draft.exists():
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("# Search Evidence Draft\n\nRun `python app.py search-plan` first.\n", encoding="utf-8")
    gaps = project / "research" / "search-evidence-gaps.md"
    if not gaps.exists():
        gaps.parent.mkdir(parents=True, exist_ok=True)
        gaps.write_text("# Search Evidence Gaps\n\nRun `python app.py search-plan` first.\n", encoding="utf-8")


def main() -> int:
    for project in sorted(p for p in PROJECTS.iterdir() if p.is_dir()):
        copy_runtime(project)
        update_manifest(project)
        update_runtime_doc(project)
        ensure_new_files(project)
        print(project.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
