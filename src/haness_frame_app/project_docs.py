from __future__ import annotations

import datetime as dt
import json
import pathlib
from functools import lru_cache
from string import Template

from .db import DEFAULT_ROLE_OPTIONS, default_project_settings, project_service_snapshot
from .paths import project_dir, slugify, write_project_doc, write_project_file

TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=None)
def load_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def render_template(name: str, **values: str) -> str:
    return Template(load_template(name)).safe_substitute(**values)


def build_project_readme(project_name: str, working_description: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return render_template(
        "project-readme.md",
        project_name=project_name,
        working_description=working_description,
        created_at=created_at,
    )


def request_language(original_request: str) -> str:
    for char in original_request:
        codepoint = ord(char)
        if 0x1100 <= codepoint <= 0x11FF or 0x3130 <= codepoint <= 0x318F or 0xAC00 <= codepoint <= 0xD7AF:
            return "ko"
    return "en"


def build_project_readme_ko(project_name: str, working_description: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return render_template(
        "project-readme.ko.md",
        project_name=project_name,
        working_description=working_description,
        created_at=created_at,
    )


def build_original_request(original_request: str, working_description: str) -> str:
    return render_template(
        "original-request.md",
        original_request=original_request,
        working_description=working_description,
    )


def build_workflow_doc(working_description: str) -> str:
    return render_template("workflow.md", working_description=working_description)


def build_business_context(working_description: str) -> str:
    return render_template("business-context.md", working_description=working_description)


def build_agent_routing(working_description: str, assignments: dict[str, str]) -> str:
    rows = []
    for role in [
        "project_scout",
        "context_curator",
        "researcher",
        "planner",
        "designer",
        "architect",
        "critic",
        "debugger",
        "decision_maker",
        "coder",
        "reviewer",
        "escalation",
    ]:
        rows.append(f"- {role}: {assignments.get(role, '')}")
    return render_template(
        "agent-routing.md",
        working_description=working_description,
        rows="\n".join(rows),
    )


def build_search_backlog(working_description: str) -> str:
    return render_template("search-backlog.md", working_description=working_description)


def build_discovery_doc(working_description: str) -> str:
    return render_template("discovery.md", working_description=working_description)


def build_role_discussion_doc(working_description: str) -> str:
    return render_template("role-discussion.md", working_description=working_description)


def build_decision_record(working_description: str) -> str:
    return render_template("decision-record.md", working_description=working_description)


def build_role_briefs(working_description: str) -> str:
    return render_template("role-briefs.md", working_description=working_description)


def build_implementation_readme(working_description: str) -> str:
    return render_template("implementation-readme.md", working_description=working_description)


def build_project_roadmap_doc(working_description: str) -> str:
    return render_template("project-roadmap.md", working_description=working_description)


def build_workspace_readme(project_name: str, working_description: str) -> str:
    return render_template(
        "workspace-readme.md",
        project_name=project_name,
        working_description=working_description,
    )


def build_workspace_state_json(
    project_name: str,
    working_description: str,
    original_request: str,
    assignments: dict[str, str],
) -> str:
    payload = {
        "project_name": project_name,
        "working_description": working_description,
        "original_request": original_request,
        "role_assignments": assignments,
        "default_roles": DEFAULT_ROLE_OPTIONS,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "bootstrap",
        "current_stage": "context",
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_workspace_manifest_json(
    project_name: str,
    working_description: str,
    original_request: str,
) -> str:
    localized_readmes = ["README.ko.md"] if request_language(original_request) == "ko" else []
    payload = {
        "project_name": project_name,
        "working_description": working_description,
        "original_request": original_request,
        "format_version": "1.0",
        "files": [
            "AGENTS.md",
            "CLAUDE.md",
            *localized_readmes,
            ".codex/skills/haness-frame/SKILL.md",
            ".codex/skills/haness-frame/skill.json",
            "workspace/state.json",
            "workspace/services.json",
            "workspace/scorecard.json",
            "workspace/evidence/search-evidence.json",
            "workspace/evidence/claim-evidence.json",
            "workspace/evidence/search-plan.json",
            "workspace/evidence-policy.json",
            "workspace/verification-policy.json",
            "workspace/repair-policy.json",
            "workspace/orchestration-policy.json",
            "workspace/search-policy.json",
            "workspace/archive-policy.json",
            "research/search-evidence-draft.md",
            "research/search-evidence-gaps.md",
            "workspace/logs/audit.jsonl",
            "docs/00-runtime-map.md",
            "docs/07-roadmap.md",
            "src/harness_app/audit.py",
            "src/harness_app/services.py",
            "src/harness_app/evidence.py",
            "src/harness_app/claims.py",
            "src/harness_app/provenance.py",
            "src/harness_app/evidence_policy.py",
            "src/harness_app/evidence_fetch.py",
            "src/harness_app/diagnostics.py",
            "src/harness_app/scorecard.py",
            "src/harness_app/manifest.py",
            "src/harness_app/snapshots.py",
            "src/harness_app/search.py",
            "src/harness_app/debate.py",
            "src/harness_app/archive.py",
            "src/harness_app/decision.py",
            "src/harness_app/prompting.py",
            "src/harness_app/client.py",
            "src/harness_app/workflow.py",
            "src/harness_app/orchestration.py",
            "src/harness_app/orchestration_plan_validation.py",
            "src/harness_app/orchestration_recovery.py",
            "src/harness_app/orchestration_policy.py",
            "src/harness_app/verification.py",
            "src/harness_app/patching.py",
            "src/harness_app/repair.py",
            "src/harness_app/finish.py",
            "src/harness_app/implementation.py",
            "src/harness_app/ai_cache.py",
            "src/harness_app/budget.py",
            "src/harness_app/qualification.py",
            "src/harness_app/network_safety.py",
            "src/harness_app/search_discovery.py",
            "src/harness_app/session_overview.py",
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_workspace_scorecard_json(project_name: str) -> str:
    payload = {
        "project_name": project_name,
        "status": "bootstrap",
        "checks": {
            "status": False,
            "next": False,
            "render": False,
            "evidence": False,
            "claim_evidence": False,
            "evidence_fetch": False,
            "decision_gate": False,
            "pipeline": False,
            "manifest": False,
            "snapshot": False,
            "rollback": False,
            "search_plan": False,
            "search_discovery": False,
            "debate": False,
            "debate_rounds": False,
            "archive": False,
            "archive_integrity": False,
            "compileall": False,
            "services": False,
            "qualification": False,
            "verification_commands": False,
            "patch_apply": False,
            "patch_rollback": False,
            "repair_loop": False,
        },
        "last_updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_workspace_services_json(project_name: str, assignments: dict[str, str]) -> str:
    payload = {
        "project_name": project_name,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "role_service_assignments": assignments,
    }
    payload.update(project_service_snapshot(assignments))
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_pyproject_toml(project_name: str) -> str:
    package_name = "harness_app"
    safe_name = slugify(project_name)
    return f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{safe_name}-harness"
version = "0.1.0"
description = "Runnable harness engineering workspace"
requires-python = ">=3.11"

[project.scripts]
harness-app = "{package_name}.cli:main"

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]
"""


def build_app_py() -> str:
    return render_template("app.py")


def build_run_ps1() -> str:
    return render_template("run.ps1")


def build_runtime_map_doc(project_name: str, working_description: str) -> str:
    return render_template(
        "runtime-map.md",
        project_name=project_name,
        working_description=working_description,
    )


def build_agents_md(project_name: str, working_description: str) -> str:
    return render_template(
        "agents.md",
        project_name=project_name,
        working_description=working_description,
    )


def build_claude_md(project_name: str, working_description: str) -> str:
    return render_template(
        "claude.md",
        project_name=project_name,
        working_description=working_description,
    )


def build_skill_md(project_name: str, working_description: str) -> str:
    return render_template(
        "skill.md",
        project_name=project_name,
        working_description=working_description,
    )


def build_skill_manifest() -> str:
    return """{
  "name": "haness-frame",
  "version": "0.1.0"
}
"""


RUNTIME_TEMPLATE_DIR = TEMPLATE_DIR / "runtime"


def build_runtime_module(name: str) -> str:
    return (RUNTIME_TEMPLATE_DIR / name).read_text(encoding="utf-8")


def build_runtime_files(base: pathlib.Path) -> dict[pathlib.Path, str]:
    runtime_dir = base / "src" / "harness_app"
    return {
        runtime_dir / "__init__.py": build_runtime_module("__init__.py"),
        runtime_dir / "__main__.py": build_runtime_module("__main__.py"),
        runtime_dir / "audit.py": build_runtime_module("audit.py"),
        runtime_dir / "services.py": build_runtime_module("services.py"),
        runtime_dir / "evidence.py": build_runtime_module("evidence.py"),
        runtime_dir / "claims.py": build_runtime_module("claims.py"),
        runtime_dir / "provenance.py": build_runtime_module("provenance.py"),
        runtime_dir / "evidence_policy.py": build_runtime_module("evidence_policy.py"),
        runtime_dir / "evidence_fetch.py": build_runtime_module("evidence_fetch.py"),
        runtime_dir / "diagnostics.py": build_runtime_module("diagnostics.py"),
        runtime_dir / "scorecard.py": build_runtime_module("scorecard.py"),
        runtime_dir / "manifest.py": build_runtime_module("manifest.py"),
        runtime_dir / "snapshots.py": build_runtime_module("snapshots.py"),
        runtime_dir / "search.py": build_runtime_module("search.py"),
        runtime_dir / "debate.py": build_runtime_module("debate.py"),
        runtime_dir / "archive.py": build_runtime_module("archive.py"),
        runtime_dir / "decision.py": build_runtime_module("decision.py"),
        runtime_dir / "prompting.py": build_runtime_module("prompting.py"),
        runtime_dir / "client.py": build_runtime_module("client.py"),
        runtime_dir / "workflow.py": build_runtime_module("workflow.py"),
        runtime_dir / "orchestration.py": build_runtime_module("orchestration.py"),
        runtime_dir / "orchestration_plan_validation.py": build_runtime_module(
            "orchestration_plan_validation.py"
        ),
        runtime_dir / "orchestration_recovery.py": build_runtime_module("orchestration_recovery.py"),
        runtime_dir / "orchestration_policy.py": build_runtime_module("orchestration_policy.py"),
        runtime_dir / "verification.py": build_runtime_module("verification.py"),
        runtime_dir / "patching.py": build_runtime_module("patching.py"),
        runtime_dir / "repair.py": build_runtime_module("repair.py"),
        runtime_dir / "finish.py": build_runtime_module("finish.py"),
        runtime_dir / "implementation.py": build_runtime_module("implementation.py"),
        runtime_dir / "ai_cache.py": build_runtime_module("ai_cache.py"),
        runtime_dir / "budget.py": build_runtime_module("budget.py"),
        runtime_dir / "qualification.py": build_runtime_module("qualification.py"),
        runtime_dir / "network_safety.py": build_runtime_module("network_safety.py"),
        runtime_dir / "search_discovery.py": build_runtime_module("search_discovery.py"),
        runtime_dir / "session_overview.py": build_runtime_module("session_overview.py"),
        runtime_dir / "storage.py": build_runtime_module("storage.py"),
        runtime_dir / "roles.py": build_runtime_module("roles.py"),
        runtime_dir / "engine.py": build_runtime_module("engine.py"),
        runtime_dir / "cli.py": build_runtime_module("cli.py"),
    }


def build_project_settings_doc(project_name: str, working_description: str, assignments: dict[str, str]) -> str:
    rows = [f"- {role}: {service}" for role, service in assignments.items()]
    return f"""# Project Settings

Project:

```text
{project_name}
```

Working description:

```text
{working_description}
```

## Role To Service Mapping

{chr(10).join(rows)}

## Notes

Update this file from the project settings page. The browser stores the UI
language in a cookie and this project file stores the role-to-service mapping.
"""


def create_project_files(
    project: str,
    original_request: str,
    english_description: str,
    force: bool,
) -> tuple[pathlib.Path, int, int]:
    working_description = english_description.strip() or original_request
    base = project_dir(project, working_description)
    project_name = project or base.name
    assignments = default_project_settings()["role_assignments"]
    localized_files: dict[pathlib.Path, str] = {}
    if request_language(original_request) == "ko":
        localized_files[base / "README.ko.md"] = build_project_readme_ko(
            project_name,
            original_request.strip() or working_description,
        )
    files = {
        base / "README.md": build_project_readme(project_name, working_description),
        **localized_files,
        base / "pyproject.toml": build_pyproject_toml(project_name),
        base / "app.py": build_app_py(),
        base / "run.ps1": build_run_ps1(),
        base / "AGENTS.md": build_agents_md(project_name, working_description),
        base / "CLAUDE.md": build_claude_md(project_name, working_description),
        base / "docs" / "00-runtime-map.md": build_runtime_map_doc(project_name, working_description),
        base / "workspace" / "README.md": build_workspace_readme(project_name, working_description),
        base / "workspace" / "state.json": build_workspace_state_json(
            project_name, working_description, original_request, assignments
        ),
        base / "workspace" / "services.json": build_workspace_services_json(project_name, assignments),
        base / "workspace" / "manifest.json": build_workspace_manifest_json(
            project_name, working_description, original_request
        ),
        base / "workspace" / "scorecard.json": build_workspace_scorecard_json(project_name),
        base / "workspace" / "evidence" / "search-evidence.json": "[]\n",
        base / "workspace" / "evidence" / "claim-evidence.json": "[]\n",
        base / "workspace" / "evidence" / "search-plan.json": json.dumps(
            {"provider": "google", "searches": []},
            indent=2,
            ensure_ascii=False,
        ),
        base / "workspace" / "evidence-policy.json": json.dumps(
            {
                "min_records": 2,
                "min_distinct_urls": 2,
                "allowed_confidence": ["high", "medium"],
                "max_age_days": 3650,
                "max_future_skew_minutes": 10,
                "min_excerpt_chars": 20,
                "min_search_coverage_ratio": 0.0,
                "require_claim_matrix": True,
                "require_decision_snapshot": True,
                "min_claims": 1,
                "min_supporting_sources_per_claim": 1,
                "require_challenge_resolution": True,
                "allowed_claim_confidence": ["high", "medium"],
                "fetch_enabled": True,
                "fetch_timeout_seconds": 10,
                "fetch_max_bytes": 1000000,
                "fetch_excerpt_chars": 1200,
                "fetch_allowed_content_types": ["text/html", "text/plain", "application/json"],
                "fetch_allowed_domains": [],
                "allow_private_network": False,
                "require_source_fingerprint": True,
                "require_source_revalidation": False,
                "max_source_verification_age_days": 30,
                "max_source_checks_per_run": 20,
            },
            indent=2,
            ensure_ascii=False,
        ),
        base / "workspace" / "verification-policy.json": json.dumps(
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
        base / "workspace" / "repair-policy.json": json.dumps(
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
        base / "workspace" / "orchestration-policy.json": json.dumps(
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
        base / "workspace" / "search-policy.json": json.dumps(
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
        base / "workspace" / "archive-policy.json": json.dumps(
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
        base / "workspace" / "logs" / "audit.jsonl": "",
        base / ".codex" / "skills" / "haness-frame" / "SKILL.md": build_skill_md(
            project_name, working_description
        ),
        base / ".codex" / "skills" / "haness-frame" / "skill.json": build_skill_manifest(),
        **build_runtime_files(base),
        base / "context" / "original-request.md": build_original_request(original_request, working_description),
        base / "docs" / "00-workflow.md": build_workflow_doc(working_description),
        base / "context" / "business-context.md": build_business_context(working_description),
        base / "context" / "source-materials.md": "# Source Materials\n\n",
        base / "research" / "search-backlog.md": build_search_backlog(working_description),
        base / "research" / "search-evidence.md": "# Search Evidence\n\nNo evidence captured yet.\n",
        base / "research" / "search-evidence-draft.md": "# Search Evidence Draft\n\nRun `python app.py search-plan` first.\n",
        base / "research" / "search-evidence-gaps.md": "# Search Evidence Gaps\n\nRun `python app.py search-plan` first.\n",
        base / "docs" / "01-project-discovery.md": build_discovery_doc(working_description),
        base / "docs" / "02-role-discussion.md": build_role_discussion_doc(working_description),
        base / "docs" / "03-decision-record.md": build_decision_record(working_description),
        base / "docs" / "04-agent-routing.md": build_agent_routing(working_description, assignments),
        base / "prompts" / "role-briefs.md": build_role_briefs(working_description),
        base / "implementation" / "README.md": build_implementation_readme(working_description),
        base / "docs" / "07-roadmap.md": build_project_roadmap_doc(working_description),
        base / "project-settings.json": json.dumps(
            {
                "role_assignments": assignments,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        base / "docs" / "05-project-settings.md": build_project_settings_doc(
            project_name, working_description, assignments
        ),
        base / "docs" / "06-system-runtime.md": f"""# 06 System Runtime

This project includes a runnable harness engine package.

## Commands

```text
python -m harness_app init
python -m harness_app check
python -m harness_app live-check --role planner
python -m harness_app status
python -m harness_app roles
python -m harness_app role-plan --task "Describe the requested work"
python -m harness_app orchestrate --stage planning --task "Describe the requested work"
python -m harness_app orchestrate --stage debate --task "Compare implementation options"
python -m harness_app orchestrate --stage repair --task "Fix the approved implementation"
python -m harness_app orchestrate-status --id latest
python -m harness_app orchestrate-resume --id EXECUTION_ID
python -m harness_app orchestrate-reconcile --id EXECUTION_ID
python -m harness_app orchestrate-reconcile-all --limit 100
python -m harness_app orchestrate-abandon --id EXECUTION_ID --reason "Superseded orchestration"
python -m harness_app pack --role planner
python -m harness_app render
python -m harness_app add-evidence --query "..." --provider "google" --url "https://example.com" --title "..." --excerpt "..." --confidence "medium" --why-it-matters "..." --recommended-use "..."
python -m harness_app evidence
python -m harness_app evidence-check
python -m harness_app evidence-fetch --url URL --query QUERY --why-it-matters REASON --recommended-use USE
python -m harness_app evidence-source-check --url URL
python -m harness_app evidence-source-check-all
python -m harness_app evidence-source-refresh --url URL
python -m harness_app claim-add --claim "..." --support-url "https://example.com/source"
python -m harness_app claim-check
python -m harness_app claims
python -m harness_app gate
python -m harness_app scorecard
python -m harness_app audit
python -m harness_app audit-check
python -m harness_app audit-export
python -m harness_app manifest
python -m harness_app search-plan
python -m harness_app evidence-draft
python -m harness_app evidence-gaps
python -m harness_app evidence-commit
python -m harness_app debate
python -m harness_app debate-rounds --prompt "Compare the implementation options" --rounds 2
python -m harness_app debate-status --id latest
python -m harness_app debate-resume --id DEBATE_ID
python -m harness_app debate-abandon --id DEBATE_ID --reason "Superseded by corrected requirements"
python -m harness_app snapshot
python -m harness_app rollback
python -m harness_app archive
python -m harness_app archive-verify
python -m harness_app decision-template
python -m harness_app decision-draft
python -m harness_app verify
python -m harness_app verification-plan
python -m harness_app verification-run
python -m harness_app patch-plan --file workspace/candidate.diff
python -m harness_app patch-apply --file workspace/candidate.diff
python -m harness_app patch-rollback --id PATCH_ID
python -m harness_app repair-run --task "Fix the failing implementation"
python -m harness_app repair-status
python -m harness_app repair-resume --id SESSION_ID
python -m harness_app repair-abandon --id SESSION_ID --reason "Superseded repair"
python -m harness_app invoke --role planner --prompt "Summarize the project state"
python -m harness_app invoke --role planner --prompt "Summarize the project state" --json
python -m harness_app pipeline --prompt "Draft a first-pass design plan"
python -m harness_app pipeline-status --id latest
python -m harness_app pipeline-resume --id RUN_ID
python -m harness_app pipeline-abandon --id RUN_ID --reason "Superseded run"
python -m harness_app runs --unresolved
python -m harness_app ai-cache-status
python -m harness_app ai-cache-prune --max-age-seconds 86400
```

## Runtime State

The runtime workspace stores live execution state in `workspace/state.json`
and rendered role packets under `workspace/packs/`. The `invoke` command uses
the role packet plus the supplied prompt to assemble the model messages.
Run `python app.py check` before `invoke` so the local model endpoints are
reachable.
The `pipeline` command writes a durable run session and per-role checkpoints to
`workspace/executions/runs/`. Use `pipeline-status` to inspect a run and
`pipeline-resume` to continue from its first unfinished role without repeating
completed AI calls. `workspace/orchestration-policy.json` bounds role count,
prompt and system size, carried context, elapsed time, and cumulative AI calls.
The run checkpoint preserves both selected limits and consumed budget. The
policy rejects role outputs outside `min_output_chars` and `max_output_chars`
before they can be handed to the next role. Coder and
reviewer roles are blocked until structured search evidence exists and
`docs/03-decision-record.md` includes an accepted decision, evidence, an
implementation brief, and verification commands.
`qualify` treats unresolved or corrupt latest pipeline runs as readiness
blockers. Use `pipeline-abandon` with a reason to explicitly resolve a
superseded failed run without marking it completed.
`debate-rounds` stores a structured decision-maker verdict with its canonical
SHA-256. `decision-draft` verifies the hash and carries the accepted decision,
rationale, risks, implementation brief, and proposed verification commands into
the decision record. Proposed commands still require exact policy approval.
The report binds the verdict to the evidence, claim, and policy digest. Verdict
`claim_ids` must reference accepted claims, and required accepted claims cannot
be omitted. Rerun the debate whenever verified knowledge changes.
Debate rounds and the judge stage are checkpointed. `debate-resume` continues a
failed linked pipeline or retries only the judge without repeating completed
rounds. Evidence changes before judgment produce a terminal stale session, and
unresolved or corrupt latest debate sessions block qualification readiness.
The orchestration policy also limits total debate rounds, elapsed time, and AI
calls. Reserved role and judge calls remain consumed across failure and resume;
budget exhaustion is terminal and blocks qualification readiness.
Use `debate-abandon` with a reason to resolve an intentionally superseded
unfinished session. Abandoned sessions are audit logged and cannot be resumed.
Hash-valid legacy debate checkpoints without global budget fields are upgraded
on load with conservative usage accounting before they can resume.
Runtime checkpoints use flushed temporary files and atomic replacement under
file locks. Audit, scorecard, evidence, and claim mutations are serialized.
PID-owned session locks prevent concurrent resume or abandon of the same
pipeline, debate, or repair run and recover locks left by dead processes.
When a process stops before updating a duplicated latest checkpoint, loaders
and qualification recover the newest durable session original by `updated_at`.
Pipeline calls persist an in-flight reservation and cache contract-valid success
before the role checkpoint, allowing crash recovery without a duplicate provider
call or AI-call budget charge. Identical concurrent cache misses are single-flight:
one caller invokes the provider and waiters reuse the saved success while retaining
their own pipeline budget reservations. `ai-cache-status` reports counts and bytes
without prompt or response content. `ai-cache-prune` removes stale or malformed
entries under the same key locks; `--all` explicitly includes fresh entries.
Use `runs --unresolved` for one content-redacted view of pipeline, debate, and
repair checkpoints with progress, failure reasons, and safe next commands.
Qualification blocks on an unresolved latest repair. `repair-abandon` records a
reason and rolls back any active patch first; rollback conflicts remain blocked.
Qualification scans all durable sessions so newer success cannot hide older
unresolved work. Successful repair handoff closes the predecessor as `superseded`
with its successor ID while preserving the successor as latest.
Direct URL capture stores a SHA-256 fingerprint of normalized visible text.
`evidence-source-check` detects later content or redirect changes without storing
the fetched body. New projects require fingerprints for direct URL records.
Detected changes block evidence policy and qualification. After review,
`evidence-source-refresh` replaces the record and verification, which also
invalidates the prior decision snapshot until the decision is regenerated.
`evidence-source-check-all` checks every fingerprinted HTTP source within the
policy run limit, continues after individual failures, and reports incomplete
or changed batches as failures without storing source bodies.
`orchestrate` executes deterministic planning, debate, or repair stages only
after their required services and decision gate pass. The stages reuse the
existing durable budgets, checkpoints, cache, resume, and rollback engines.
Each invocation stores a content-redacted orchestration execution checkpoint
that links its plan and task hash to the underlying durable session. Inspect it
with `orchestrate-status` even after a failed command.
The child session ID is reserved before stage execution, preserving a recovery
target even when the wrapper is interrupted before the stage returns.
`orchestrate-resume` hash-validates the saved plan, resumes an existing child,
or starts the missing child with its reserved ID. Completed wrappers are
idempotent and perform no additional provider work.
`orchestrate-reconcile` copies an existing child checkpoint state into the
wrapper without invoking a provider or continuing child work.
`orchestrate-reconcile-all` performs the same provider-free recovery for up to
the requested number of wrappers, while skipping active or missing children.
Wrappers complete only for stage-specific child success. Terminal non-success
results remain failed and visible even when the child returned normally.
`orchestrate` and `orchestrate-resume` exit with `0` only for completed wrappers,
and with `2` for persisted non-success results.
Repair revalidates the decision gate before reviewer work and final approval so
mid-attempt evidence or decision changes cannot produce stale approval.
Saved approval verdicts receive the same resume-time check and rollback their
applied patch when the gate has become stale.
Service diagnostics compare coder and reviewer provider, endpoint, and model.
Sharing one execution identity produces a non-blocking review-independence warning.
Set `require_independent_reviewer_service` in `repair-policy.json` to require
distinct coder/reviewer execution identities for qualification and repair.
Strict mode also compares actual invocation identities, including fallback and
cached responses, before approval and rolls back shared-identity patches.
Strict qualification revalidates durable actual identities in approved repair
checkpoints and rejects shared or incomplete identity evidence.
Approved attempts bind coder identity, reviewer identity, and verdict in
`review_provenance_sha256`; strict qualification rejects mismatches.
`require_independent_debate_judge_service` optionally requires configured and
actual judge identity to differ from all participants. `judge_provenance_sha256`
binds verdict, evidence digest, participant identities, and judge identity.
Unresolved wrappers appear in `runs --unresolved`, which recommends reconcile,
resume, or abandon from child checkpoint state, and block qualification.
`orchestrate-abandon` abandons an existing linked durable session first. The
wrapper remains unresolved if child cleanup or repair rollback fails.
""",
    }

    created = []
    skipped = []
    for path, content in files.items():
        if write_project_file(path, content, force):
            created.append(path)
        else:
            skipped.append(path)

    return base, len(created), len(skipped)


def build_design_template(task: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return render_template("design-template.md", task=task, created_at=created_at)


def build_discussion_skeleton(task: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return render_template("discussion-skeleton.md", task=task, created_at=created_at)
