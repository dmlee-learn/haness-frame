from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from .db import DEFAULT_ROLE_OPTIONS, init_db, list_ai_services
from .paths import DESIGN_LOOP, DB, ROLES, ROOT, read_config_text, task_text
from .project_docs import build_design_template, build_discussion_skeleton, create_project_files
from .web import cmd_serve


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


def cmd_design_template(args: argparse.Namespace) -> int:
    task = task_text(args.task)
    content = build_design_template(task)
    if args.write:
        from .paths import write_project_doc

        path = write_project_doc("design", args.project, task, content)
        print(path)
    else:
        print(content)
    return 0


def cmd_discuss(args: argparse.Namespace) -> int:
    task = task_text(args.task)
    content = build_discussion_skeleton(task)
    if args.write:
        from .paths import write_project_doc

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
    create_project.add_argument("--project", default="", help="Project folder name. Defaults to a slug derived from the task.")
    create_project.add_argument("--force", action="store_true", help="Overwrite existing generated project files.")
    create_project.add_argument("--english-description", default="", help="English working description used in generated harness files.")
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
    design_template.add_argument("--write", action="store_true", help="Write to projects/<project>/docs/.")
    design_template.add_argument("--project", default="", help="Project folder name. Defaults to a slug derived from the task.")
    design_template.add_argument("task", nargs=argparse.REMAINDER)
    design_template.set_defaults(func=cmd_design_template)

    discuss = subparsers.add_parser(
        "discuss",
        help="Create or print a role discussion skeleton.",
    )
    discuss.add_argument("--write", action="store_true", help="Write to projects/<project>/docs/.")
    discuss.add_argument("--project", default="", help="Project folder name. Defaults to a slug derived from the task.")
    discuss.add_argument("task", nargs=argparse.REMAINDER)
    discuss.set_defaults(func=cmd_discuss)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)

