from __future__ import annotations

import argparse
import compileall
import json
import sys

from .archive import create_archive
from .audit import log_event, recent_events
from .client import invoke
from .decision import build_decision_record_draft, write_decision_record_draft
from .engine import bootstrap, decision_gate, next_action, refresh_runtime_scorecard, render_role_packets, role_packet, status_report, summary_report
from .evidence import add_evidence, commit_evidence_draft, evidence_markdown, load_evidence, write_evidence_draft, write_evidence_gaps
from .manifest import manifest_report
from .roles import ROLE_ORDER
from .scorecard import mark_check, scorecard_report
from .search import build_search_plan, open_search
from .snapshots import create_snapshot, list_snapshots, restore_snapshot
from .storage import save_state
from .debate import debate_summary, run_debate
from .workflow import run_sequence


def print_gate() -> None:
    gate = decision_gate()
    refresh_runtime_scorecard(gate)
    print(json.dumps(gate, indent=2, ensure_ascii=False))


def run_verify() -> dict[str, object]:
    compile_ok = compileall.compile_dir("src", quiet=1)
    manifest = json.loads(manifest_report())
    gate = decision_gate()
    mark_check("compileall", compile_ok, "src")
    return {
        "compileall": compile_ok,
        "manifest": manifest,
        "gate": gate,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Bootstrap runtime workspace state.")
    init_parser.set_defaults(func=lambda args: bootstrap())

    status_parser = subparsers.add_parser("status", help="Print current harness status.")
    status_parser.set_defaults(func=lambda args: print(status_report()))

    summary_parser = subparsers.add_parser("summary", help="Print a compact harness summary with counts.")
    summary_parser.set_defaults(func=lambda args: print(summary_report()))

    roles_parser = subparsers.add_parser("roles", help="Print the role order.")
    roles_parser.set_defaults(func=lambda args: print("\n".join(ROLE_ORDER)))

    packet_parser = subparsers.add_parser("pack", help="Print a role packet.")
    packet_parser.add_argument("--role", required=True)
    packet_parser.set_defaults(func=lambda args: print(role_packet(args.role)))

    render_parser = subparsers.add_parser("render", help="Render all role packets to workspace/packs.")
    render_parser.set_defaults(func=lambda args: print("\n".join(str(path) for path in render_role_packets())))

    next_parser = subparsers.add_parser("next", help="Print the next recommended action.")
    next_parser.set_defaults(func=lambda args: print(next_action()))

    gate_parser = subparsers.add_parser("gate", help="Print the decision gate status.")
    gate_parser.set_defaults(func=lambda args: print_gate())

    scorecard_parser = subparsers.add_parser("scorecard", help="Print runtime scorecard JSON.")
    scorecard_parser.set_defaults(func=lambda args: print(scorecard_report()))

    audit_parser = subparsers.add_parser("audit", help="Print recent audit log events.")
    audit_parser.add_argument("--limit", type=int, default=20)
    audit_parser.set_defaults(func=lambda args: print(json.dumps(recent_events(args.limit), indent=2, ensure_ascii=False)))

    manifest_parser = subparsers.add_parser("manifest", help="Validate the workspace manifest.")
    manifest_parser.set_defaults(func=lambda args: print(manifest_report()))

    search_plan_parser = subparsers.add_parser("search-plan", help="Build a local search plan from the backlog.")
    search_plan_parser.add_argument("--provider", default="google")
    search_plan_parser.set_defaults(func=lambda args: print(json.dumps(build_search_plan(args.provider), indent=2, ensure_ascii=False)))

    search_open_parser = subparsers.add_parser("search-open", help="Open one search URL from the generated plan.")
    search_open_parser.add_argument("--index", type=int, default=1)
    search_open_parser.add_argument("--provider", default="google")
    search_open_parser.set_defaults(func=lambda args: print(json.dumps(open_search(args.index, args.provider), indent=2, ensure_ascii=False)))

    debate_parser = subparsers.add_parser("debate", help="Run a structured role debate.")
    debate_parser.add_argument("--prompt", required=True)
    debate_parser.add_argument("--roles", default="")
    debate_parser.add_argument("--temperature", type=float, default=0.2)
    debate_parser.add_argument("--max-tokens", type=int, default=None)
    debate_parser.add_argument("--retries", type=int, default=1)
    debate_parser.set_defaults(
        func=lambda args: print(
            debate_summary(
                run_debate(
                    args.prompt,
                    roles=[role.strip() for role in args.roles.split(",") if role.strip()] or None,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    retries=args.retries,
                )
            )
        )
    )

    snapshot_parser = subparsers.add_parser("snapshot", help="Create a workspace snapshot.")
    snapshot_parser.add_argument("--label", default="")
    snapshot_parser.set_defaults(func=lambda args: print(json.dumps(create_snapshot(args.label), indent=2, ensure_ascii=False)))

    snapshots_parser = subparsers.add_parser("snapshots", help="List available snapshots.")
    snapshots_parser.set_defaults(func=lambda args: print(json.dumps(list_snapshots(), indent=2, ensure_ascii=False)))

    rollback_parser = subparsers.add_parser("rollback", help="Restore a workspace snapshot.")
    rollback_parser.add_argument("--name", required=True)
    rollback_parser.set_defaults(func=lambda args: print(json.dumps(restore_snapshot(args.name), indent=2, ensure_ascii=False)))

    archive_parser = subparsers.add_parser("archive", help="Create a workspace archive zip.")
    archive_parser.add_argument("--label", default="")
    archive_parser.set_defaults(func=lambda args: print(str(create_archive(args.label))))

    decision_parser = subparsers.add_parser("decision-template", help="Print a decision record draft.")
    decision_parser.set_defaults(func=lambda args: print(build_decision_record_draft()))

    decision_write_parser = subparsers.add_parser("decision-draft", help="Write a decision record draft to docs/03-decision-record.md.")
    decision_write_parser.set_defaults(func=lambda args: print(write_decision_record_draft()))

    verify_parser = subparsers.add_parser("verify", help="Run local runtime verification checks.")
    verify_parser.set_defaults(func=lambda args: print(json.dumps(run_verify(), indent=2, ensure_ascii=False)))

    evidence_parser = subparsers.add_parser("evidence", help="List captured search evidence.")
    evidence_parser.set_defaults(func=lambda args: print(evidence_markdown(load_evidence())))

    evidence_draft_parser = subparsers.add_parser("evidence-draft", help="Write a search evidence draft from the current search plan.")
    evidence_draft_parser.set_defaults(func=lambda args: print(write_evidence_draft()))

    evidence_gaps_parser = subparsers.add_parser("evidence-gaps", help="Write a gap report for search plan items without evidence.")
    evidence_gaps_parser.set_defaults(func=lambda args: print(write_evidence_gaps()))

    evidence_commit_parser = subparsers.add_parser("evidence-commit", help="Commit a filled evidence draft into structured evidence.")
    evidence_commit_parser.add_argument("--file", default="research/search-evidence-draft.md")
    evidence_commit_parser.set_defaults(func=lambda args: print(json.dumps(commit_evidence_draft(args.file), indent=2, ensure_ascii=False)))

    add_evidence_parser = subparsers.add_parser("add-evidence", help="Capture one structured search evidence record.")
    add_evidence_parser.add_argument("--query", required=True)
    add_evidence_parser.add_argument("--provider", required=True)
    add_evidence_parser.add_argument("--url", required=True)
    add_evidence_parser.add_argument("--title", required=True)
    add_evidence_parser.add_argument("--excerpt", required=True)
    add_evidence_parser.add_argument("--confidence", required=True)
    add_evidence_parser.add_argument("--why-it-matters", required=True)
    add_evidence_parser.add_argument("--recommended-use", required=True)
    add_evidence_parser.add_argument("--retrieved-at", default="")
    add_evidence_parser.set_defaults(
        func=lambda args: print(
            add_evidence(
                query=args.query,
                provider=args.provider,
                url=args.url,
                title=args.title,
                excerpt=args.excerpt,
                confidence=args.confidence,
                why_it_matters=args.why_it_matters,
                recommended_use=args.recommended_use,
                retrieved_at=args.retrieved_at,
            )["url"]
        )
    )

    invoke_parser = subparsers.add_parser("invoke", help="Call one role with a prompt.")
    invoke_parser.add_argument("--role", required=True)
    invoke_parser.add_argument("--prompt", required=True)
    invoke_parser.add_argument("--system", default="")
    invoke_parser.add_argument("--temperature", type=float, default=0.2)
    invoke_parser.add_argument("--max-tokens", type=int, default=None)
    invoke_parser.add_argument("--retries", type=int, default=1)
    invoke_parser.set_defaults(
        func=lambda args: print(
            invoke(
                args.role,
                args.prompt,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retries=args.retries,
            )["content"]
        )
    )

    pipeline_parser = subparsers.add_parser("pipeline", help="Run a small role sequence and save outputs.")
    pipeline_parser.add_argument("--roles", default="planner,designer,architect")
    pipeline_parser.add_argument("--prompt", required=True)
    pipeline_parser.add_argument("--system", default="")
    pipeline_parser.add_argument("--temperature", type=float, default=0.2)
    pipeline_parser.add_argument("--max-tokens", type=int, default=None)
    pipeline_parser.add_argument("--retries", type=int, default=1)
    pipeline_parser.set_defaults(
        func=lambda args: print(
            "\n".join(
                f"{item['index']:02d} {item['role']}: {item['content'][:120]}"
                for item in run_sequence(
                    [role.strip() for role in args.roles.split(",") if role.strip()],
                    args.prompt,
                    system=args.system,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    retries=args.retries,
                )
            )
        )
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        log_event("cli.command.started", command=args.command)
        result = args.func(args)
    except (RuntimeError, ValueError) as exc:
        log_event("cli.command.failed", command=args.command, error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    log_event("cli.command.completed", command=args.command)
    if result is not None and not isinstance(result, int):
        return 0
    return int(result or 0)
