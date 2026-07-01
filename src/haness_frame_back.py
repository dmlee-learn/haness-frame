#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import pathlib
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "harness.yaml"
ROLES = ROOT / "config" / "roles.yaml"
DESIGN_LOOP = ROOT / "config" / "design_loop.yaml"
RUNS = ROOT / "runs"
PROJECTS = ROOT / "projects"
DATA = ROOT / "data"
DB = DATA / "haness.db"
LANG_DIR = ROOT / "lang"
SUPPORTED_LANGUAGES = {"en": "English", "ko": "한국어"}
DEFAULT_ROLE_OPTIONS = [
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
]


DEFAULT_AI_SERVICES = [
    {
        "name": "local-vllm",
        "company": "local",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "Qwen/Qwen3-8B-AWQ",
        "role": "fallback",
        "roles": "fallback",
        "enabled": 1,
        "notes": "Local vLLM OpenAI-compatible endpoint.",
    },
    {
        "name": "local-vllm-coder",
        "company": "local",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ",
        "role": "coder",
        "roles": "coder",
        "enabled": 0,
        "notes": "Local coder model profile.",
    },
    {
        "name": "ollama",
        "company": "local",
        "provider_type": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3.5:35b",
        "role": "planner",
        "roles": "planner,reviewer",
        "enabled": 0,
        "notes": "Local Ollama planner or reviewer endpoint.",
    },
    {
        "name": "codex",
        "company": "openai",
        "provider_type": "codex",
        "base_url": "",
        "model": "codex",
        "role": "escalation",
        "roles": "escalation,coder,reviewer",
        "enabled": 0,
        "notes": "Codex or cloud coding assistant escalation path.",
    },
    {
        "name": "claude",
        "company": "anthropic",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet",
        "role": "escalation",
        "roles": "escalation,planner,reviewer",
        "enabled": 0,
        "notes": "Claude API configuration placeholder.",
    },
]


def read_config_text() -> str:
    return CONFIG.read_text(encoding="utf-8")


def db_connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                company TEXT NOT NULL DEFAULT '',
                provider_type TEXT NOT NULL,
                base_url TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                roles TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 0,
                api_key_env TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(conn, "ai_services", "company", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "ai_services", "roles", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for service in DEFAULT_AI_SERVICES:
            conn.execute(
                """
                INSERT OR IGNORE INTO ai_services
                    (name, company, provider_type, base_url, model, role, roles, enabled, notes)
                VALUES
                    (:name, :company, :provider_type, :base_url, :model, :role, :roles, :enabled, :notes)
                """,
                service,
            )
            conn.execute(
                "UPDATE ai_services SET company = ? WHERE name = ? AND company = ''",
                (service["company"], service["name"]),
            )
        conn.execute("UPDATE ai_services SET roles = role WHERE roles = ''")
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value)
            VALUES ('default_project_language', 'en')
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value)
            VALUES ('default_ui_language', 'en')
            """
        )


def get_setting(key: str, default: str = "") -> str:
    init_db()
    with db_connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    init_db()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )


def load_language(code: str) -> dict[str, str]:
    if code not in SUPPORTED_LANGUAGES:
        code = "en"
    path = LANG_DIR / f"{code}.json"
    fallback = LANG_DIR / "en.json"
    data: dict[str, str] = {}
    if fallback.exists():
        data.update(json.loads(fallback.read_text(encoding="utf-8")))
    if path.exists() and path != fallback:
        data.update(json.loads(path.read_text(encoding="utf-8")))
    return data


def tr(lang: str, key: str) -> str:
    return load_language(lang).get(key, key)


def parse_cookies(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = urllib.parse.unquote(value.strip())
    return cookies


def normalize_language(code: str) -> str:
    return code if code in SUPPORTED_LANGUAGES else "en"


def list_ai_services() -> list[sqlite3.Row]:
    init_db()
    with db_connect() as conn:
        return list(conn.execute("SELECT * FROM ai_services ORDER BY roles, name"))


def get_ai_service(name: str) -> sqlite3.Row | None:
    init_db()
    with db_connect() as conn:
        return conn.execute("SELECT * FROM ai_services WHERE name = ?", (name,)).fetchone()


def upsert_ai_service(data: dict[str, str]) -> None:
    init_db()
    enabled = 1 if data.get("enabled") == "1" else 0
    roles = ",".join(
        role.strip()
        for role in data.get("roles", data.get("role", "")).split(",")
        if role.strip()
    )
    role = roles.split(",", 1)[0] if roles else data.get("role", "").strip()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_services
                (name, company, provider_type, base_url, model, role, roles, enabled, api_key_env, notes)
            VALUES
                (:name, :company, :provider_type, :base_url, :model, :role, :roles, :enabled, :api_key_env, :notes)
            ON CONFLICT(name) DO UPDATE SET
                company = excluded.company,
                provider_type = excluded.provider_type,
                base_url = excluded.base_url,
                model = excluded.model,
                role = excluded.role,
                roles = excluded.roles,
                enabled = excluded.enabled,
                api_key_env = excluded.api_key_env,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            {
                "name": data.get("name", "").strip(),
                "company": data.get("company", "").strip(),
                "provider_type": data.get("provider_type", "").strip(),
                "base_url": data.get("base_url", "").strip(),
                "model": data.get("model", "").strip(),
                "role": role,
                "roles": roles,
                "enabled": enabled,
                "api_key_env": data.get("api_key_env", "").strip(),
                "notes": data.get("notes", "").strip(),
            },
        )


def delete_ai_service(name: str) -> bool:
    init_db()
    with db_connect() as conn:
        result = conn.execute("DELETE FROM ai_services WHERE name = ?", (name,))
        return result.rowcount > 0


def check_url(name: str, url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            print(f"OK   {name} {url} [{response.status}]")
            return True
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL {name} {url}: {exc}")
        return False


def cmd_check(_: argparse.Namespace) -> int:
    ok = True
    ok &= check_url("vLLM", "http://127.0.0.1:8000/v1/models")
    ok &= check_url("Ollama", "http://127.0.0.1:11434/api/tags")
    return 0 if ok else 1


def cmd_show_config(_: argparse.Namespace) -> int:
    print(read_config_text())
    return 0


def cmd_roles(_: argparse.Namespace) -> int:
    print(ROLES.read_text(encoding="utf-8"))
    return 0


def cmd_design_loop(_: argparse.Namespace) -> int:
    print(DESIGN_LOOP.read_text(encoding="utf-8"))
    return 0


def cmd_planner_contract(_: argparse.Namespace) -> int:
    print((ROOT / "docs" / "prompts.md").read_text(encoding="utf-8"))
    return 0


def cmd_ollama_tags(_: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL Ollama tags: {exc}", file=sys.stderr)
        return 1

    for model in payload.get("models", []):
        name = model.get("name", "")
        size = model.get("size", 0)
        print(f"{name}\t{size}")
    return 0


def cmd_init_db(_: argparse.Namespace) -> int:
    init_db()
    print(DB)
    return 0


def cmd_services(_: argparse.Namespace) -> int:
    for service in list_ai_services():
        enabled = "on" if service["enabled"] else "off"
        print(
            f"{service['name']}\t{service['company']}\t{service['provider_type']}\t{service['roles']}\t"
            f"{service['model']}\t{service['base_url']}\t{enabled}"
        )
    return 0


def task_text(parts: list[str]) -> str:
    text = " ".join(parts).strip()
    if not text:
        raise SystemExit("task is required")
    return text


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:48] or "design"


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_project_doc(prefix: str, project: str, task: str, content: str) -> pathlib.Path:
    project_slug = slugify(project or task)
    docs_dir = PROJECTS / project_slug / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"{prefix}-{now_stamp()}-{slugify(task)}.md"
    path.write_text(content, encoding="utf-8")
    return path


def project_dir(project: str, task: str) -> pathlib.Path:
    return PROJECTS / slugify(project or task)


def safe_project_path(name: str) -> pathlib.Path | None:
    slug = slugify(name)
    if not slug or slug != name:
        return None
    path = (PROJECTS / slug).resolve()
    root = PROJECTS.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def list_projects() -> list[dict[str, str]]:
    PROJECTS.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(PROJECTS.iterdir()):
        if not path.is_dir():
            continue
        readme = path / "README.md"
        updated = dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        description = ""
        if readme.exists():
            text = readme.read_text(encoding="utf-8", errors="replace")
            marker = "## Working Description"
            if marker in text:
                description = text.split(marker, 1)[1].split("##", 1)[0].strip()
        projects.append(
            {
                "name": path.name,
                "updated": updated,
                "description": description,
            }
        )
    return projects


def project_file_rows(path: pathlib.Path) -> list[dict[str, str]]:
    rows = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(path).as_posix()
        rows.append(
            {
                "path": rel,
                "size": str(item.stat().st_size),
            }
        )
    return rows


def project_zip_bytes(path: pathlib.Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(path.rglob("*")):
            if not item.is_file():
                continue
            archive.write(item, arcname=f"{path.name}/{item.relative_to(path).as_posix()}")
    return buffer.getvalue()


def write_project_file(path: pathlib.Path, content: str, overwrite: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def build_project_readme(project_name: str, working_description: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return f"""# {project_name}

Created: {created_at}

## Working Description

{working_description}

## Harness Workflow

```text
Project Scout -> Context Curator -> Researcher -> Planner -> Designer -> Architect -> Critic -> Decision Maker -> Coder
```

## Start Here

1. Fill `context/business-context.md`.
2. Run the Google searches listed in `research/search-backlog.md`.
3. Summarize findings in `docs/01-project-discovery.md`.
4. Complete the role discussion in `docs/02-role-discussion.md`.
5. Finalize the build decision in `docs/03-decision-record.md`.
6. Give the implementation brief to the coder.

## Project Folders

```text
context/          Internal business and domain context
research/         Search backlog and external evidence
docs/             Discovery, discussion, and decision records
prompts/          Role-specific prompt briefs
implementation/  Build notes after a decision is accepted
```
"""


def build_original_request(original_request: str, working_description: str) -> str:
    return f"""# Original Request

This file stores the user-provided request. Other harness files should use the
English working description for search, planning, and implementation.

## User Request

```text
{original_request}
```

## English Working Description

```text
{working_description}
```
"""


def build_business_context(working_description: str) -> str:
    return f"""# Business Context

Working description:

```text
{working_description}
```

## Business Goal

What business problem should this system solve?

## Users

Who will use it?

## Current Workflow

How is the work handled today?

## Pain Points

What is slow, duplicated, risky, or hard to track?

## Required Capabilities

## Excluded Scope

## Constraints

Budget:

Schedule:

Security:

Compliance:

Existing systems:

## Domain Terms

## Source Materials

List internal documents, spreadsheets, screenshots, policies, or sample data
that should be injected into role prompts.
"""


def build_search_backlog(working_description: str) -> str:
    return f"""# Search Backlog

Before design starts, Project Scout must search for related systems,
alternatives, architecture examples, and common failures.

## Required Google Searches

```text
{working_description} existing projects
{working_description} open source github
{working_description} alternatives
{working_description} architecture
{working_description} common problems
{working_description} workflow examples
{working_description} database schema examples
{working_description} security considerations
```

## Evidence Format

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
why_it_matters:
recommended_use:
```

## Findings

### Related Projects

### Existing Products

### Open Source Repositories

### Architecture Examples

### Common Problems

### Useful Patterns

### Risks To Avoid
"""


def build_discovery_doc(working_description: str) -> str:
    return f"""# 01 Project Discovery

Working description:

```text
{working_description}
```

## Project Scout Summary

## Related Projects

## Existing Products

## Open Source References

## Reusable Ideas

## Risks To Avoid

## Recommended Direction Before Planning

## Evidence

Copy structured search evidence from `research/search-backlog.md`.
"""


def build_role_discussion_doc(working_description: str) -> str:
    return f"""# 02 Role Discussion

Working description:

```text
{working_description}
```

## Context Curator

Internal context packet:

Missing business facts:

## Researcher

External evidence summary:

Open research questions:

## Planner

Goals:

Non-goals:

Constraints:

Design options:

## Designer

User workflow:

Information structure:

UX risks:

## Architect

System boundaries:

Data model:

Integrations:

Operational risks:

## Critic

Blocking risks:

Weak assumptions:

Required tests:

## Decision Maker

Proceed:

Required changes before coding:
"""


def build_decision_record(working_description: str) -> str:
    return f"""# 03 Decision Record

Working description:

```text
{working_description}
```

## Accepted Decision

## Context

## Evidence Used

## Rejected Options

## Implementation Brief For Coder

## Verification Commands

## Rollback Plan

## Open Questions
"""


def build_role_briefs(working_description: str) -> str:
    return f"""# Role Briefs

Working description:

```text
{working_description}
```

## Project Scout

Search first. Find related systems, alternatives, architecture examples, and
common failures before planning starts.

## Context Curator

Prepare the business context packet from internal documents, user constraints,
domain terms, sample data, and existing workflow.

## Planner

Use discovery and context to produce options. Do not generate code.

## Designer

Define user workflow, screens or CLI flow, information structure, and confusing
states.

## Architect

Define system boundaries, data flow, integrations, and technical risks.

## Critic

Challenge assumptions, missing evidence, missing tests, and risky complexity.

## Decision Maker

Select one design and produce the implementation brief.

## Coder

Implement only after the accepted decision exists.
"""


def build_implementation_readme(working_description: str) -> str:
    return f"""# Implementation Notes

Do not start implementation until `docs/03-decision-record.md` contains an
accepted decision and implementation brief.

Working description:

```text
{working_description}
```

## Build Plan

## Test Plan

## Change Log
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
    files = {
        base / "README.md": build_project_readme(project_name, working_description),
        base / "context" / "original-request.md": build_original_request(original_request, working_description),
        base / "context" / "business-context.md": build_business_context(working_description),
        base / "context" / "source-materials.md": "# Source Materials\n\n",
        base / "research" / "search-backlog.md": build_search_backlog(working_description),
        base / "docs" / "01-project-discovery.md": build_discovery_doc(working_description),
        base / "docs" / "02-role-discussion.md": build_role_discussion_doc(working_description),
        base / "docs" / "03-decision-record.md": build_decision_record(working_description),
        base / "prompts" / "role-briefs.md": build_role_briefs(working_description),
        base / "implementation" / "README.md": build_implementation_readme(working_description),
    }

    created = []
    skipped = []
    for path, content in files.items():
        if write_project_file(path, content, force):
            created.append(path)
        else:
            skipped.append(path)

    return base, len(created), len(skipped)


def cmd_create_project(args: argparse.Namespace) -> int:
    task = task_text(args.task)
    base, created, skipped = create_project_files(
        project=args.project,
        original_request=task,
        english_description=args.english_description,
        force=args.force,
    )
    print(base)
    print(f"created: {created}")
    print(f"skipped: {skipped}")
    if skipped:
        print("Use --force to overwrite existing files.")
    return 0


def nav_html(lang: str) -> str:
    return (
        f'<nav><a href="/">{html.escape(tr(lang, "nav.create_project"))}</a> | '
        f'<a href="/projects">{html.escape(tr(lang, "nav.projects"))}</a> | '
        f'<a href="/settings">{html.escape(tr(lang, "nav.ai_services"))}</a> | '
        f'<a href="/preferences">{html.escape(tr(lang, "nav.preferences"))}</a></nav>'
    )


def project_form_html(message: str = "", lang: str = "en") -> str:
    escaped_message = html.escape(message)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame project creator</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 880px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 18px; }}
    input, textarea {{ width: 100%; box-sizing: border-box; font: inherit; padding: 10px; margin-top: 6px; }}
    textarea {{ min-height: 120px; }}
    button {{ margin-top: 20px; padding: 10px 16px; font: inherit; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
    .hint {{ color: #444; font-size: 0.95rem; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "project.title"))}</h1>
  <p class="hint">{html.escape(tr(lang, "project.hint"))} <code>context/original-request.md</code>.</p>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <form method="post" accept-charset="utf-8">
    <label for="project">{html.escape(tr(lang, "project.folder_name"))}</label>
    <input id="project" name="project" placeholder="internal-business-system" required>

    <label for="english_description">{html.escape(tr(lang, "project.english_description"))}</label>
    <textarea id="english_description" name="english_description" required placeholder="Build an internal business system for approvals, task requests, document management, messaging, leave requests, and organization management"></textarea>

    <label for="original_request">{html.escape(tr(lang, "project.original_request"))}</label>
    <textarea id="original_request" name="original_request" placeholder="Original request in any language"></textarea>

    <label>
      <input type="checkbox" name="force" value="1" style="width:auto">
      {html.escape(tr(lang, "project.overwrite"))}
    </label>

    <button type="submit">{html.escape(tr(lang, "project.create_button"))}</button>
  </form>
</body>
</html>
"""


def projects_html(message: str = "", lang: str = "en") -> str:
    rows = []
    for project in list_projects():
        name = html.escape(project["name"])
        description = html.escape(project["description"])
        updated = html.escape(project["updated"])
        url_name = urllib.parse.quote(project["name"])
        rows.append(
            "<tr>"
            f"<td><a href='/project?name={url_name}'>{name}</a></td>"
            f"<td>{description}</td>"
            f"<td>{updated}</td>"
            f"<td><a href='/download?name={url_name}'>Download ZIP</a></td>"
            "</tr>"
        )
    escaped_message = html.escape(message)
    body_rows = "".join(rows) if rows else "<tr><td colspan='4'>No projects yet.</td></tr>"
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame projects</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "projects.title"))}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <table>
    <thead>
      <tr><th>{html.escape(tr(lang, "common.name"))}</th><th>{html.escape(tr(lang, "projects.working_description"))}</th><th>{html.escape(tr(lang, "projects.updated"))}</th><th>{html.escape(tr(lang, "projects.download"))}</th></tr>
    </thead>
    <tbody>{body_rows}</tbody>
  </table>
</body>
</html>
"""


def project_detail_html(name: str, message: str = "", lang: str = "en") -> str:
    path = safe_project_path(name)
    if path is None:
        return projects_html(f"Project not found: {name}", lang)
    rows = []
    for file_info in project_file_rows(path):
        rows.append(
            "<tr>"
            f"<td>{html.escape(file_info['path'])}</td>"
            f"<td>{html.escape(file_info['size'])}</td>"
            "</tr>"
        )
    escaped_name = html.escape(name)
    escaped_message = html.escape(message)
    url_name = urllib.parse.quote(name)
    body_rows = "".join(rows) if rows else "<tr><td colspan='2'>No files.</td></tr>"
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{escaped_name}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <p><a href="/download?name={url_name}">{html.escape(tr(lang, "projects.download_zip"))}</a></p>
  <p><code>{html.escape(str(path))}</code></p>
  <table>
    <thead>
      <tr><th>{html.escape(tr(lang, "project_detail.file"))}</th><th>{html.escape(tr(lang, "project_detail.size"))}</th></tr>
    </thead>
    <tbody>{body_rows}</tbody>
  </table>
</body>
</html>
"""


def provider_options(selected: str) -> str:
    providers = [
        "openai_compatible",
        "vllm",
        "ollama",
        "codex",
        "anthropic",
        "openai",
        "gemini",
        "other",
    ]
    return "".join(
        f'<option value="{provider}"{" selected" if provider == selected else ""}>{provider}</option>'
        for provider in providers
    )


def language_options(selected: str) -> str:
    return "".join(
        f'<option value="{code}"{" selected" if code == selected else ""}>{html.escape(label)}</option>'
        for code, label in SUPPORTED_LANGUAGES.items()
    )


def preferences_html(message: str = "", lang: str = "en") -> str:
    default_lang = normalize_language(get_setting("default_ui_language", "en"))
    escaped_message = html.escape(message)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(tr(lang, "preferences.title"))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 880px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 18px; }}
    select {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; margin-top: 4px; }}
    button {{ margin-top: 18px; padding: 10px 16px; font: inherit; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "preferences.title"))}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <form method="post" action="/preferences" accept-charset="utf-8">
    <label for="user_language">{html.escape(tr(lang, "preferences.user_language"))}</label>
    <select id="user_language" name="user_language">{language_options(lang)}</select>
    <button type="submit" name="action" value="save_user_language">{html.escape(tr(lang, "preferences.save_user_language"))}</button>
  </form>
  <form method="post" action="/preferences" accept-charset="utf-8">
    <label for="default_language">{html.escape(tr(lang, "preferences.default_language"))}</label>
    <select id="default_language" name="default_language">{language_options(default_lang)}</select>
    <button type="submit" name="action" value="save_default_language">{html.escape(tr(lang, "preferences.save_default_language"))}</button>
  </form>
</body>
</html>
"""


def settings_html(message: str = "", lang: str = "en", edit_name: str = "") -> str:
    services = list_ai_services()
    edit_service = get_ai_service(edit_name) if edit_name else None
    edit_roles = set((edit_service["roles"] if edit_service else "").split(","))
    rows = []
    for service in services:
        url_name = urllib.parse.quote(service["name"])
        rows.append(
            "<tr>"
            f"<td>{html.escape(service['name'])}</td>"
            f"<td>{html.escape(service['company'])}</td>"
            f"<td>{html.escape(service['provider_type'])}</td>"
            f"<td>{html.escape(service['roles'])}</td>"
            f"<td>{html.escape(service['model'])}</td>"
            f"<td>{html.escape(service['base_url'])}</td>"
            f"<td>{'yes' if service['enabled'] else 'no'}</td>"
            f"<td>{html.escape(service['api_key_env'])}</td>"
            f"<td>{html.escape(service['notes'])}</td>"
            f"<td><a href='/settings?edit={url_name}'>{html.escape(tr(lang, 'common.edit'))}</a> "
            f"<form method='post' action='/settings' style='display:inline'>"
            f"<input type='hidden' name='action' value='delete'>"
            f"<input type='hidden' name='name' value='{html.escape(service['name'])}'>"
            f"<button type='submit'>{html.escape(tr(lang, 'common.delete'))}</button></form></td>"
            "</tr>"
        )
    escaped_message = html.escape(message)
    role_boxes = []
    for role in DEFAULT_ROLE_OPTIONS:
        checked = " checked" if role in edit_roles else ""
        role_boxes.append(
            f"<label style='font-weight:400'><input type='checkbox' name='roles' value='{role}' style='width:auto'{checked}> {role}</label>"
        )
    form_value = lambda key: html.escape(edit_service[key]) if edit_service else ""
    enabled_checked = " checked" if edit_service and edit_service["enabled"] else ""
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame AI services</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 14px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; margin-top: 4px; }}
    textarea {{ min-height: 70px; }}
    button {{ margin-top: 18px; padding: 10px 16px; font: inherit; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; font-size: 0.92rem; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "settings.title"))}</h1>
  <p>{html.escape(tr(lang, "settings.db_hint"))} <code>{html.escape(str(DB))}</code>. {html.escape(tr(lang, "settings.key_hint"))}</p>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}

  <h2>{html.escape(tr(lang, "settings.configured_services"))}</h2>
  <table>
    <thead>
      <tr>
        <th>{html.escape(tr(lang, "common.name"))}</th><th>{html.escape(tr(lang, "settings.company"))}</th><th>{html.escape(tr(lang, "settings.provider"))}</th><th>{html.escape(tr(lang, "settings.roles"))}</th><th>{html.escape(tr(lang, "settings.model"))}</th><th>{html.escape(tr(lang, "settings.base_url"))}</th><th>{html.escape(tr(lang, "settings.enabled"))}</th><th>{html.escape(tr(lang, "settings.api_key_env"))}</th><th>{html.escape(tr(lang, "settings.notes"))}</th><th>{html.escape(tr(lang, "common.actions"))}</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>{html.escape(tr(lang, "settings.edit_service"))}</h2>
  <form method="post" action="/settings" accept-charset="utf-8">
    <input type="hidden" name="action" value="save">
    <div class="grid">
      <div>
        <label for="name">{html.escape(tr(lang, "common.name"))}</label>
        <input id="name" name="name" placeholder="local-vllm" value="{form_value('name')}" required>
      </div>
      <div>
        <label for="company">{html.escape(tr(lang, "settings.company"))}</label>
        <input id="company" name="company" placeholder="openai, anthropic, local" value="{form_value('company')}">
      </div>
      <div>
        <label for="provider_type">{html.escape(tr(lang, "settings.provider"))}</label>
        <select id="provider_type" name="provider_type">
          {provider_options(form_value('provider_type'))}
        </select>
      </div>
      <div>
        <label>{html.escape(tr(lang, "settings.roles"))}</label>
        {''.join(role_boxes)}
      </div>
      <div>
        <label for="model">{html.escape(tr(lang, "settings.model"))}</label>
        <input id="model" name="model" placeholder="Qwen/Qwen3-8B-AWQ" value="{form_value('model')}">
      </div>
      <div>
        <label for="base_url">{html.escape(tr(lang, "settings.base_url"))}</label>
        <input id="base_url" name="base_url" placeholder="http://127.0.0.1:8000/v1" value="{form_value('base_url')}">
      </div>
      <div>
        <label for="api_key_env">{html.escape(tr(lang, "settings.api_key_env"))}</label>
        <input id="api_key_env" name="api_key_env" placeholder="ANTHROPIC_API_KEY" value="{form_value('api_key_env')}">
      </div>
    </div>
    <label>
      <input type="checkbox" name="enabled" value="1" style="width:auto"{enabled_checked}>
      {html.escape(tr(lang, "settings.enabled"))}
    </label>
    <label for="notes">{html.escape(tr(lang, "settings.notes"))}</label>
    <textarea id="notes" name="notes">{form_value('notes')}</textarea>
    <button type="submit">{html.escape(tr(lang, "settings.save_service"))}</button>
  </form>
</body>
</html>
"""


class ProjectServer(BaseHTTPRequestHandler):
    def current_language(self) -> str:
        cookies = parse_cookies(self.headers.get("Cookie", ""))
        raw_cookie_lang = cookies.get("haness_lang", "")
        if raw_cookie_lang in SUPPORTED_LANGUAGES:
            return raw_cookie_lang
        return normalize_language(get_setting("default_ui_language", "en"))

    def send_html(self, body: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_bytes(self, payload: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        lang = self.current_language()
        if parsed.path == "/settings":
            edit_name = query.get("edit", [""])[0]
            self.send_html(settings_html(lang=lang, edit_name=edit_name))
            return
        if parsed.path == "/preferences":
            self.send_html(preferences_html(lang=lang))
            return
        if parsed.path == "/projects":
            self.send_html(projects_html(lang=lang))
            return
        if parsed.path == "/project":
            name = query.get("name", [""])[0]
            self.send_html(project_detail_html(name, lang=lang))
            return
        if parsed.path == "/download":
            name = query.get("name", [""])[0]
            path = safe_project_path(name)
            if path is None:
                self.send_html(projects_html(f"Project not found: {name}", lang), 404)
                return
            payload = project_zip_bytes(path)
            self.send_bytes(payload, "application/zip", f"{path.name}.zip")
            return
        if parsed.path != "/":
            self.send_html(project_form_html("Use / to create a project.", lang), 404)
            return
        self.send_html(project_form_html(lang=lang))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        lang = self.current_language()
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(raw_body, keep_blank_values=True)

        if parsed.path == "/settings":
            action = form.get("action", ["save"])[0]
            if action == "delete":
                name = form.get("name", [""])[0].strip()
                if name:
                    delete_ai_service(name)
                self.send_html(settings_html(f"Deleted service: {name}", lang))
                return
            data = {key: values[0] for key, values in form.items()}
            data["roles"] = ",".join(form.get("roles", []))
            if not data.get("name") or not data.get("provider_type"):
                self.send_html(settings_html("Name and provider type are required.", lang), 400)
                return
            upsert_ai_service(data)
            self.send_html(settings_html(f"Saved service: {data.get('name', '').strip()}", lang))
            return

        if parsed.path == "/preferences":
            action = form.get("action", [""])[0]
            if action == "save_default_language":
                selected = normalize_language(form.get("default_language", ["en"])[0])
                set_setting("default_ui_language", selected)
                self.send_html(preferences_html("Default language saved.", selected))
                return
            selected = normalize_language(form.get("user_language", ["en"])[0])
            headers = {"Set-Cookie": f"haness_lang={urllib.parse.quote(selected)}; Path=/; SameSite=Lax"}
            self.send_html(preferences_html("User language saved in cookie.", selected), headers=headers)
            return

        if parsed.path != "/":
            self.send_html(project_form_html("Use / to create a project.", lang), 404)
            return

        project = form.get("project", [""])[0].strip()
        english_description = form.get("english_description", [""])[0].strip()
        original_request = form.get("original_request", [""])[0].strip() or english_description
        force = form.get("force", [""])[0] == "1"

        if not project or not english_description:
            self.send_html(project_form_html("Project and English working description are required.", lang), 400)
            return

        base, created, skipped = create_project_files(
            project=project,
            original_request=original_request,
            english_description=english_description,
            force=force,
        )
        message = f"Project harness created.\n\nPath: {base}\nCreated: {created}\nSkipped: {skipped}"
        message += f"\n\nManage: /project?name={base.name}\nDownload: /download?name={base.name}"
        if skipped:
            message += "\n\nEnable overwrite if you want to replace existing generated files."
        self.send_html(project_form_html(message, lang))


def cmd_serve(args: argparse.Namespace) -> int:
    init_db()
    server = HTTPServer((args.host, args.port), ProjectServer)
    url = f"http://{args.host}:{args.port}/"
    print(f"haness-frame project creator: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


def build_design_template(task: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return f"""# Design Session

Task: {task}
Created: {created_at}

## 1. Project Discovery - Project Scout

Before planning, search Google for related projects and alternatives.

Required Google searches:

1. {task} existing projects
2. {task} open source github
3. {task} alternatives
4. {task} architecture
5. {task} common problems

Related projects:

Existing products:

Open source repositories:

Useful implementation patterns:

Risks to avoid:

Evidence:

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

## 2. Intake - Planner

Goals:

Non-goals:

Constraints:

Unknowns:

Repository context to inspect:

Discovery summary to use:

## 3. Research Questions - Researcher

All roles may search when current evidence or alternatives are needed.
Default provider: Google.

Search queries by role:

Project Scout:

Researcher:

Planner:

Designer:

Architect:

Critic:

Debugger:

Coder:

Decision Maker:

Alternative searches:

## 4. Internet Evidence - Researcher

Use this schema for each source:

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

Verified facts:

Assumptions:

Open questions:

Design impact:

## 5. Proposal - Planner

Option A:

Option B:

Option C:

Recommended option:

## 6. Experience Design - Designer

User flow:

Information structure:

Usability risks:

Search needed:

## 7. Architecture Review - Architect

Tradeoff matrix:

Integration risks:

Operational risks:

Recommendation:

## 8. Adversarial Review - Critic

Blocking risks:

Weak assumptions:

Missing tests:

Can proceed:

## 9. Debate Round

Resolved points:

Unresolved points:

Required changes:

## 10. Decision - Decision Maker

Accepted decision:

Rejected options:

Implementation brief:

Verification commands:

Rollback plan:
"""


def build_discussion_skeleton(task: str) -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return f"""# Role Discussion

Task: {task}
Created: {created_at}

## Project Scout

Before planning, search Google for related projects and alternatives.

Required searches:

1. {task} existing projects
2. {task} open source github
3. {task} alternatives
4. {task} architecture
5. {task} common problems

Discovery summary:

- Related projects:
- Existing products:
- Open source repositories:
- Useful patterns:
- Risks to avoid:

Evidence format:

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

## Researcher

I coordinate evidence, but every role may search when needed.

Baseline searches:

1.
2.
3.

Evidence format:

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

## Planner

Initial framing:

- Goals:
- Non-goals:
- Constraints:
- Unknowns:

Candidate designs:

- Option A:
- Option B:
- Option C:

Search needed:

## Designer

Experience design:

- User flow:
- Information structure:
- Confusing states:
- Recommended simplifications:

Search needed:

## Architect

Architecture review:

- Fit with existing code:
- Interfaces:
- Data flow:
- Operational cost:
- Recommended option:

Search needed:

## Critic

Blocking concerns:

- Missing evidence:
- Failure modes:
- Tests required:
- Proceed or revise:

Search needed:

## Decision Maker

Decision:

Implementation brief for coder:

Verification commands:

Rollback plan:
"""


def cmd_design_template(args: argparse.Namespace) -> int:
    task = task_text(args.task)
    content = build_design_template(task)
    if args.write:
        path = write_project_doc("design", args.project, task, content)
        print(path)
    else:
        print(content)
    return 0


def cmd_discuss(args: argparse.Namespace) -> int:
    task = task_text(args.task)
    content = build_discussion_skeleton(task)
    if args.write:
        path = write_project_doc("discussion", args.project, task, content)
        print(path)
    else:
        print(content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="haness-frame")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Check local model endpoints.")
    check.set_defaults(func=cmd_check)

    show_config = subparsers.add_parser("show-config", help="Print harness config.")
    show_config.set_defaults(func=cmd_show_config)

    roles = subparsers.add_parser("roles", help="Print role definitions.")
    roles.set_defaults(func=cmd_roles)

    design_loop = subparsers.add_parser("design-loop", help="Print design loop config.")
    design_loop.set_defaults(func=cmd_design_loop)

    prompts = subparsers.add_parser("prompts", help="Print role prompt contracts.")
    prompts.set_defaults(func=cmd_planner_contract)

    tags = subparsers.add_parser("ollama-tags", help="List installed Ollama models.")
    tags.set_defaults(func=cmd_ollama_tags)

    init_database = subparsers.add_parser("init-db", help="Initialize the local SQLite settings database.")
    init_database.set_defaults(func=cmd_init_db)

    services = subparsers.add_parser("services", help="List configured AI services.")
    services.set_defaults(func=cmd_services)

    create_project = subparsers.add_parser(
        "create-project",
        help="Create a project-specific harness engineering workspace.",
    )
    create_project.add_argument(
        "--project",
        default="",
        help="Project folder name. Defaults to a slug derived from the task.",
    )
    create_project.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated project files.",
    )
    create_project.add_argument(
        "--english-description",
        default="",
        help="English working description used in generated harness files.",
    )
    create_project.add_argument("task", nargs=argparse.REMAINDER)
    create_project.set_defaults(func=cmd_create_project)

    serve = subparsers.add_parser(
        "serve",
        help="Start a local UTF-8 web form for project creation.",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)

    design_template = subparsers.add_parser(
        "design-template",
        help="Create or print a design discussion template.",
    )
    design_template.add_argument(
        "--write",
        action="store_true",
        help="Write to projects/<project>/docs/.",
    )
    design_template.add_argument(
        "--project",
        default="",
        help="Project folder name. Defaults to a slug derived from the task.",
    )
    design_template.add_argument("task", nargs=argparse.REMAINDER)
    design_template.set_defaults(func=cmd_design_template)

    discuss = subparsers.add_parser(
        "discuss",
        help="Create or print a role discussion skeleton.",
    )
    discuss.add_argument(
        "--write",
        action="store_true",
        help="Write to projects/<project>/docs/.",
    )
    discuss.add_argument(
        "--project",
        default="",
        help="Project folder name. Defaults to a slug derived from the task.",
    )
    discuss.add_argument("task", nargs=argparse.REMAINDER)
    discuss.set_defaults(func=cmd_discuss)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
