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
    payload = {
        "project_name": project_name,
        "working_description": working_description,
        "original_request": original_request,
        "format_version": "1.0",
        "files": [
            "AGENTS.md",
            "CLAUDE.md",
            ".codex/skills/haness-frame/SKILL.md",
            ".codex/skills/haness-frame/skill.json",
            "workspace/state.json",
            "workspace/services.json",
            "workspace/scorecard.json",
            "workspace/evidence/search-evidence.json",
            "workspace/evidence/search-plan.json",
            "research/search-evidence-draft.md",
            "research/search-evidence-gaps.md",
            "workspace/logs/audit.jsonl",
            "docs/00-runtime-map.md",
            "docs/07-roadmap.md",
            "src/harness_app/audit.py",
            "src/harness_app/services.py",
            "src/harness_app/evidence.py",
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
            "decision_gate": False,
            "pipeline": False,
            "manifest": False,
            "snapshot": False,
            "rollback": False,
            "search_plan": False,
            "debate": False,
            "archive": False,
            "compileall": False,
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
    files = {
        base / "README.md": build_project_readme(project_name, working_description),
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
        base / "workspace" / "evidence" / "search-plan.json": json.dumps(
            {"provider": "google", "searches": []},
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
python -m harness_app status
python -m harness_app summary
python -m harness_app roles
python -m harness_app pack --role planner
python -m harness_app render
python -m harness_app add-evidence --query "..." --provider "google" --url "https://example.com" --title "..." --excerpt "..." --confidence "medium" --why-it-matters "..." --recommended-use "..."
python -m harness_app evidence
python -m harness_app gate
python -m harness_app scorecard
python -m harness_app audit
python -m harness_app manifest
python -m harness_app search-plan
python -m harness_app evidence-draft
python -m harness_app evidence-gaps
python -m harness_app evidence-commit
python -m harness_app debate
python -m harness_app snapshot
python -m harness_app rollback
python -m harness_app archive
python -m harness_app decision-template
python -m harness_app decision-draft
python -m harness_app verify
python -m harness_app invoke --role planner --prompt "Summarize the project state"
python -m harness_app pipeline --prompt "Draft a first-pass design plan"
```

## Runtime State

The runtime workspace stores live execution state in `workspace/state.json`
and rendered role packets under `workspace/packs/`. The `invoke` command uses
the role packet plus the supplied prompt to assemble the model messages.
Run `python app.py check` before `invoke` so the local model endpoints are
reachable.
The `pipeline` command writes outputs to `workspace/executions/`. Coder and
reviewer roles are blocked until structured search evidence exists and
`docs/03-decision-record.md` includes an accepted decision, evidence, an
implementation brief, and verification commands.
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
