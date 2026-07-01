from __future__ import annotations

import datetime as dt
import json
import pathlib
from functools import lru_cache
from string import Template

from .db import DEFAULT_ROLE_OPTIONS, default_project_settings, project_service_snapshot
from .paths import PROJECTS, project_dir, slugify, task_text, write_project_doc, write_project_file

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
            "docs/00-runtime-map.md",
            "docs/07-roadmap.md",
        "src/harness_app/services.py",
        "src/harness_app/prompting.py",
        "src/harness_app/client.py",
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


def build_harness_package_init() -> str:
    return """from .cli import main
"""


def build_harness_package_main() -> str:
    return """from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_harness_services_module() -> str:
    return """from __future__ import annotations

import json

from .storage import read_text


def load_services() -> dict[str, object]:
    payload = read_text("workspace/services.json", "{}")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def role_service(role: str) -> dict[str, object]:
    payload = load_services()
    role_services = payload.get("role_services", {})
    if not isinstance(role_services, dict):
        return {}
    service = role_services.get(role, {})
    return service if isinstance(service, dict) else {}


def fallback_service() -> dict[str, object]:
    payload = load_services()
    service = payload.get("fallback_service", {})
    return service if isinstance(service, dict) else {}
"""


def build_harness_client_module() -> str:
    return """from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .prompting import build_messages
from .services import fallback_service, role_service


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_content(content: str) -> str:
    text = _THINK_BLOCK.sub("", content or "")
    return text.strip()


def _api_key_headers(service: dict[str, object]) -> dict[str, str]:
    env_name = str(service.get("api_key_env", "") or "").strip()
    if not env_name:
        return {}
    api_key = os.getenv(env_name, "").strip()
    if not api_key:
        return {}
    provider_type = str(service.get("provider_type", "") or "").strip()
    if provider_type == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {api_key}"}


def _post_json(url: str, payload: dict[str, object], headers: dict[str, str] | None = None, timeout: int = 60) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _openai_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in messages
    ]


def _openai_compatible(service: dict[str, object], messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    base_url = str(service.get("base_url", "") or "").rstrip("/")
    model = str(service.get("model", "") or "").strip()
    if not base_url or not model:
        raise ValueError("service base_url and model are required")
    payload: dict[str, object] = {
        "model": model,
        "messages": _openai_messages(messages),
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    response = _post_json(
        f"{base_url}/chat/completions",
        payload,
        headers=_api_key_headers(service),
    )
    return response


def _ollama(service: dict[str, object], messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    base_url = str(service.get("base_url", "") or "").rstrip("/")
    model = str(service.get("model", "") or "").strip()
    if not base_url or not model:
        raise ValueError("service base_url and model are required")
    payload: dict[str, object] = {
        "model": model,
        "messages": _openai_messages(messages),
        "stream": False,
        "options": {"temperature": temperature},
    }
    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens
    return _post_json(f"{base_url}/api/chat", payload)


def _same_service(left: dict[str, object], right: dict[str, object]) -> bool:
    return (
        str(left.get("name", "")) == str(right.get("name", ""))
        and str(left.get("provider_type", "")) == str(right.get("provider_type", ""))
        and str(left.get("base_url", "")) == str(right.get("base_url", ""))
        and str(left.get("model", "")) == str(right.get("model", ""))
    )


def _invoke_service(service: dict[str, object], messages: list[dict[str, str]], temperature: float, max_tokens: int | None) -> dict[str, object]:
    provider_type = str(service.get("provider_type", "") or "").strip()
    if provider_type in {"openai_compatible", "openai", "vllm", "codex"}:
        response = _openai_compatible(service, messages, temperature=temperature, max_tokens=max_tokens)
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _clean_content(str(message.get("content", ""))),
            "raw": response,
        }
    if provider_type == "ollama":
        response = _ollama(service, messages, temperature=temperature, max_tokens=max_tokens)
        message = response.get("message") or {}
        return {
            "service": service,
            "provider_type": provider_type,
            "content": _clean_content(str(message.get("content", ""))),
            "raw": response,
        }
    raise ValueError(f"unsupported provider type: {provider_type}")


def call_role(role: str, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    service = role_service(role)
    if not service:
        raise ValueError(f"no service configured for role: {role}")
    try:
        return _invoke_service(service, messages, temperature, max_tokens)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        fallback = fallback_service()
        if fallback and not _same_service(service, fallback):
            result = _invoke_service(fallback, messages, temperature, max_tokens)
            result["fallback_error"] = str(exc)
            return result
        raise


def invoke(role: str, prompt: str, system: str = "", temperature: float = 0.2, max_tokens: int | None = None) -> dict[str, object]:
    return call_role(
        role,
        build_messages(role, prompt, system=system),
        temperature=temperature,
        max_tokens=max_tokens,
    )
"""


def build_harness_prompting_module() -> str:
    return """from __future__ import annotations

from .engine import role_packet


def build_messages(role: str, prompt: str, system: str = "") -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    packet = role_packet(role).strip()
    system_parts = [part for part in [packet, system.strip()] if part]
    if system_parts:
        messages.append({"role": "system", "content": "\\n\\n".join(system_parts)})
    messages.append({"role": "user", "content": prompt})
    return messages
"""


def build_harness_storage_module() -> str:
    return """from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace"
STATE_FILE = WORKSPACE / "state.json"


def ensure_workspace() -> None:
    for rel in ["packs", "evidence", "decisions"]:
        (WORKSPACE / rel).mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, object]:
    ensure_workspace()
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, object]) -> None:
    ensure_workspace()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def read_text(rel_path: str, default: str = "") -> str:
    path = ROOT / rel_path
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(rel_path: str, content: str) -> pathlib.Path:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
"""


def build_harness_roles_module() -> str:
    roles = [
        ("project_scout", "Searches for related systems, alternatives, and failure modes."),
        ("context_curator", "Assembles the business context and internal evidence."),
        ("researcher", "Collects supporting evidence and citations."),
        ("planner", "Turns evidence into options and tradeoffs."),
        ("designer", "Defines user flows and interaction constraints."),
        ("architect", "Checks boundaries, data flow, and operational fit."),
        ("critic", "Challenges assumptions and missing tests."),
        ("decision_maker", "Chooses the accepted option and the implementation brief."),
        ("coder", "Implements the accepted plan."),
        ("reviewer", "Validates the implementation result."),
        ("escalation", "Handles outside-model or higher-risk decisions."),
    ]
    body = "\n".join([f'    "{name}": "{summary}",' for name, summary in roles])
    order = ", ".join([f'"{name}"' for name, _ in roles])
    return f"""ROLE_ORDER = [{order}]

ROLE_SUMMARIES = {{
{body}
}}


def describe_role(role: str) -> str:
    return ROLE_SUMMARIES.get(role, "")
"""


def build_harness_engine_module() -> str:
    return """from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .roles import ROLE_ORDER, describe_role
from .storage import ROOT, STATE_FILE, ensure_workspace, load_state, read_text, save_state, write_text

REQUIRED_DOCS = [
    "context/business-context.md",
    "context/source-materials.md",
    "research/search-backlog.md",
    "docs/01-project-discovery.md",
    "docs/02-role-discussion.md",
    "docs/03-decision-record.md",
]


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
    decision_text = read_text("docs/03-decision-record.md", "")
    accepted = decision_text.split("## Accepted Decision", 1)
    if len(accepted) == 2:
        tail = accepted[1]
        next_heading = tail.find("\\n## ")
        if next_heading != -1:
            tail = tail[:next_heading]
        if tail.strip():
            return "Decision approved. Move to implementation."
    return "Finish the decision record before coding."


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
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- none")
    return "\\n".join(lines)


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
    return outputs
"""


def build_harness_cli_module() -> str:
    return """from __future__ import annotations

import argparse

from .client import invoke
from .engine import bootstrap, next_action, render_role_packets, role_packet, status_report
from .roles import ROLE_ORDER
from .storage import save_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Bootstrap runtime workspace state.")
    init_parser.set_defaults(func=lambda args: bootstrap())

    status_parser = subparsers.add_parser("status", help="Print current harness status.")
    status_parser.set_defaults(func=lambda args: print(status_report()))

    roles_parser = subparsers.add_parser("roles", help="Print the role order.")
    roles_parser.set_defaults(func=lambda args: print("\\n".join(ROLE_ORDER)))

    packet_parser = subparsers.add_parser("pack", help="Print a role packet.")
    packet_parser.add_argument("--role", required=True)
    packet_parser.set_defaults(func=lambda args: print(role_packet(args.role)))

    render_parser = subparsers.add_parser("render", help="Render all role packets to workspace/packs.")
    render_parser.set_defaults(func=lambda args: print("\\n".join(str(path) for path in render_role_packets())))

    next_parser = subparsers.add_parser("next", help="Print the next recommended action.")
    next_parser.set_defaults(func=lambda args: print(next_action()))

    invoke_parser = subparsers.add_parser("invoke", help="Call one role with a prompt.")
    invoke_parser.add_argument("--role", required=True)
    invoke_parser.add_argument("--prompt", required=True)
    invoke_parser.add_argument("--system", default="")
    invoke_parser.add_argument("--temperature", type=float, default=0.2)
    invoke_parser.add_argument("--max-tokens", type=int, default=None)
    invoke_parser.set_defaults(
        func=lambda args: print(
            invoke(
                args.role,
                args.prompt,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )["content"]
        )
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    if result is not None and not isinstance(result, int):
        return 0
    return int(result or 0)
"""


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
        base / ".codex" / "skills" / "haness-frame" / "SKILL.md": build_skill_md(
            project_name, working_description
        ),
        base / ".codex" / "skills" / "haness-frame" / "skill.json": build_skill_manifest(),
        base / "src" / "harness_app" / "__init__.py": build_harness_package_init(),
        base / "src" / "harness_app" / "__main__.py": build_harness_package_main(),
        base / "src" / "harness_app" / "services.py": build_harness_services_module(),
        base / "src" / "harness_app" / "prompting.py": build_harness_prompting_module(),
        base / "src" / "harness_app" / "client.py": build_harness_client_module(),
        base / "src" / "harness_app" / "storage.py": build_harness_storage_module(),
        base / "src" / "harness_app" / "roles.py": build_harness_roles_module(),
        base / "src" / "harness_app" / "engine.py": build_harness_engine_module(),
        base / "src" / "harness_app" / "cli.py": build_harness_cli_module(),
        base / "context" / "original-request.md": build_original_request(original_request, working_description),
        base / "docs" / "00-workflow.md": build_workflow_doc(working_description),
        base / "context" / "business-context.md": build_business_context(working_description),
        base / "context" / "source-materials.md": "# Source Materials\n\n",
        base / "research" / "search-backlog.md": build_search_backlog(working_description),
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
python -m harness_app status
python -m harness_app roles
python -m harness_app pack --role planner
python -m harness_app render
python -m harness_app invoke --role planner --prompt "Summarize the project state"
```

## Runtime State

The runtime workspace stores live execution state in `workspace/state.json`
and rendered role packets under `workspace/packs/`. The `invoke` command uses
the role packet plus the supplied prompt to assemble the model messages.
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
