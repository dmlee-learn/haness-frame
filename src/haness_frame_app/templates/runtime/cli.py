from __future__ import annotations

import argparse
import compileall
import json
import sys

from .archive import create_archive, verify_archive
from .ai_cache import cache_status, prune_cache
from .audit import audit_check, export_audit, log_event, recent_events
from .client import RoleInvocationError, invocation_report, invoke
from .claims import add_claim, claim_policy_report, claims_markdown
from .decision import build_decision_record_draft, write_decision_record_draft
from .diagnostics import print_live_check, print_service_check
from .engine import bootstrap, decision_gate, next_action, refresh_runtime_scorecard, render_role_packets, role_packet, status_report, summary_report
from .evidence import add_evidence, commit_evidence_draft, evidence_markdown, evidence_policy_report, load_evidence, rebuild_evidence_markdown, write_evidence_draft, write_evidence_gaps
from .evidence_fetch import fetch_evidence, refresh_evidence_source, verify_all_evidence_sources, verify_evidence_source
from .finish import finish_project
from .implementation import implement_project
from .manifest import manifest_report, print_manifest_report
from .orchestration import abandon_orchestration_execution, build_role_plan, execute_task, load_orchestration_execution, reconcile_orchestration_execution, resume_orchestration_execution
from .orchestration_recovery import reconcile_orchestration_executions
from .patching import apply_patch_text, load_patch_file, patch_plan_report, rollback_patch
from .qualification import print_qualification
from .roles import ROLE_ORDER
from .repair import abandon_repair_loop, load_repair_session, resume_repair_loop, run_repair_loop
from .scorecard import mark_check, scorecard_report
from .search import build_search_plan, open_search
from .search_discovery import discover_sources
from .session_overview import session_overview
from .snapshots import create_snapshot, list_snapshots, restore_snapshot
from .storage import save_state
from .debate import abandon_debate_rounds, debate_summary, load_debate_session, resume_debate_rounds, run_debate, run_debate_rounds
from .workflow import abandon_sequence, load_pipeline_session, resume_sequence, run_sequence
from .verification import run_verification_commands, verification_plan


def print_gate() -> int:
    gate = decision_gate()
    refresh_runtime_scorecard(gate)
    print(json.dumps(gate, indent=2, ensure_ascii=False))
    return 0 if gate["allowed"] else 1


def print_audit_check() -> int:
    report = audit_check()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_invoke(args: argparse.Namespace) -> None:
    result = invoke(
        args.role,
        args.prompt,
        system=args.system,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        retries=args.retries,
    )
    if args.json:
        print(json.dumps(invocation_report(result), indent=2, ensure_ascii=False))
    else:
        print(result["content"])


def print_evidence_source_check(args: argparse.Namespace) -> int:
    report = verify_evidence_source(args.url)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_evidence_source_check_all(args: argparse.Namespace) -> int:
    report = verify_all_evidence_sources(args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_evidence_check() -> int:
    report = evidence_policy_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_claim_check() -> int:
    report = claim_policy_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_archive_verify(args: argparse.Namespace) -> int:
    report = verify_archive(args.file)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def print_verification_plan() -> int:
    report = verification_plan()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["approved"] else 1


def print_verification_run(args: argparse.Namespace) -> int:
    report = run_verification_commands(stop_on_failure=not args.continue_on_failure)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


def print_verify() -> int:
    report = run_verify()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    valid = bool(
        report["compileall"]
        and report["manifest"].get("valid")
        and report["gate"].get("allowed")
    )
    return 0 if valid else 1


def print_finish(args: argparse.Namespace) -> int:
    report = finish_project(label=args.label)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 2


def print_implementation(args: argparse.Namespace) -> int:
    report = implement_project(
        args.task,
        max_tokens=args.max_tokens,
        retries=args.retries,
        label=args.label,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 2


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


def print_pipeline_results(results: list[dict[str, object]]) -> None:
    if results:
        print(f"run_id: {results[0]['run_id']}")
    print("\n".join(f"{item['index']:02d} {item['role']}: {str(item['content'])[:120]}" for item in results))


def print_orchestration_run(result: dict[str, object]) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    execution = result.get("execution", result)
    status = str(execution.get("status", "")) if isinstance(execution, dict) else ""
    return 0 if status == "completed" else 2


def print_orchestration_reconcile_all(args: argparse.Namespace) -> int:
    report = reconcile_orchestration_executions(limit=args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report.get("failures") else 0


def print_repair_result(result: dict[str, object]) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in {"approved", "already_verified"} else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Bootstrap runtime workspace state.")
    init_parser.set_defaults(func=lambda args: bootstrap())

    check_parser = subparsers.add_parser("check", help="Validate role service settings and optionally probe unique endpoints.")
    check_parser.add_argument("--no-probe", action="store_true")
    check_parser.add_argument("--timeout", type=float, default=2.0)
    check_parser.set_defaults(
        func=lambda args: print_service_check(probe=not args.no_probe, timeout=args.timeout)
    )

    live_check_parser = subparsers.add_parser(
        "live-check", help="Probe configured services and perform one content-redacted role call."
    )
    live_check_parser.add_argument("--role", default="planner")
    live_check_parser.add_argument("--timeout", type=float, default=2.0)
    live_check_parser.add_argument("--max-tokens", type=int, default=32)
    live_check_parser.add_argument("--retries", type=int, default=0)
    live_check_parser.set_defaults(
        func=lambda args: print_live_check(
            role=args.role,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            retries=args.retries,
        )
    )

    qualify_parser = subparsers.add_parser("qualify", help="Run one consolidated project readiness and qualification report.")
    qualify_parser.add_argument("--probe-services", action="store_true")
    qualify_parser.add_argument("--run-verification", action="store_true")
    qualify_parser.add_argument("--service-timeout", type=float, default=2.0)
    qualify_parser.set_defaults(
        func=lambda args: print_qualification(
            probe_services=args.probe_services,
            run_verification=args.run_verification,
            service_timeout=args.service_timeout,
        )
    )

    status_parser = subparsers.add_parser("status", help="Print current harness status.")
    status_parser.set_defaults(func=lambda args: print(status_report()))

    summary_parser = subparsers.add_parser("summary", help="Print a compact harness summary with counts.")
    summary_parser.set_defaults(func=lambda args: print(summary_report()))

    runs_parser = subparsers.add_parser("runs", help="Summarize durable pipeline, debate, and repair sessions.")
    runs_parser.add_argument("--limit", type=int, default=20)
    runs_parser.add_argument("--unresolved", action="store_true")
    runs_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                session_overview(limit=args.limit, unresolved_only=args.unresolved),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

    roles_parser = subparsers.add_parser("roles", help="Print the role order.")
    roles_parser.set_defaults(func=lambda args: print("\n".join(ROLE_ORDER)))

    role_plan_parser = subparsers.add_parser("role-plan", help="Build a deterministic task-to-role orchestration plan.")
    role_plan_parser.add_argument("--task", required=True)
    role_plan_parser.set_defaults(
        func=lambda args: print(json.dumps(build_role_plan(args.task), indent=2, ensure_ascii=False))
    )

    orchestrate_parser = subparsers.add_parser(
        "orchestrate", help="Plan and execute one validated planning, debate, or repair stage."
    )
    orchestrate_parser.add_argument("--task", required=True)
    orchestrate_parser.add_argument("--stage", choices=["planning", "debate", "repair"], default="planning")
    orchestrate_parser.add_argument("--rounds", type=int, default=2)
    orchestrate_parser.add_argument("--retries", type=int, default=1)
    orchestrate_parser.add_argument("--max-attempts", type=int, default=None)
    orchestrate_parser.set_defaults(
        func=lambda args: print_orchestration_run(
            execute_task(
                args.task,
                stage=args.stage,
                rounds=args.rounds,
                retries=args.retries,
                max_attempts=args.max_attempts,
            )
        )
    )

    orchestrate_status_parser = subparsers.add_parser(
        "orchestrate-status", help="Inspect one content-redacted orchestration execution checkpoint."
    )
    orchestrate_status_parser.add_argument("--id", default="latest")
    orchestrate_status_parser.set_defaults(
        func=lambda args: print(
            json.dumps(load_orchestration_execution(args.id), indent=2, ensure_ascii=False)
        )
    )

    orchestrate_resume_parser = subparsers.add_parser(
        "orchestrate-resume", help="Resume the linked stage or start its reserved child session after interruption."
    )
    orchestrate_resume_parser.add_argument("--id", required=True)
    orchestrate_resume_parser.set_defaults(
        func=lambda args: print_orchestration_run(resume_orchestration_execution(args.id))
    )

    orchestrate_reconcile_parser = subparsers.add_parser(
        "orchestrate-reconcile", help="Reconcile a wrapper from its child checkpoint without running AI work."
    )
    orchestrate_reconcile_parser.add_argument("--id", required=True)
    orchestrate_reconcile_parser.set_defaults(
        func=lambda args: print_orchestration_run(reconcile_orchestration_execution(args.id))
    )

    orchestrate_reconcile_all_parser = subparsers.add_parser(
        "orchestrate-reconcile-all", help="Reconcile terminal child checkpoints for multiple wrappers."
    )
    orchestrate_reconcile_all_parser.add_argument("--limit", type=int, default=100)
    orchestrate_reconcile_all_parser.set_defaults(func=print_orchestration_reconcile_all)

    orchestrate_abandon_parser = subparsers.add_parser(
        "orchestrate-abandon", help="Explicitly close a failed or interrupted orchestration wrapper."
    )
    orchestrate_abandon_parser.add_argument("--id", required=True)
    orchestrate_abandon_parser.add_argument("--reason", required=True)
    orchestrate_abandon_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                abandon_orchestration_execution(args.id, args.reason),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

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

    audit_check_parser = subparsers.add_parser("audit-check", help="Validate every audit JSONL record and timestamp.")
    audit_check_parser.set_defaults(func=lambda args: print_audit_check())

    audit_export_parser = subparsers.add_parser("audit-export", help="Export validated audit history to workspace/reports.")
    audit_export_parser.add_argument("--filename", default="")
    audit_export_parser.set_defaults(func=lambda args: print(str(export_audit(args.filename))))

    cache_status_parser = subparsers.add_parser("ai-cache-status", help="Report AI cache counts and size without response content.")
    cache_status_parser.add_argument("--max-age-seconds", type=int, default=86400)
    cache_status_parser.set_defaults(
        func=lambda args: print(json.dumps(cache_status(args.max_age_seconds), indent=2, ensure_ascii=False))
    )

    cache_prune_parser = subparsers.add_parser("ai-cache-prune", help="Remove expired or invalid AI cache entries.")
    cache_prune_parser.add_argument("--max-age-seconds", type=int, default=86400)
    cache_prune_parser.add_argument("--all", action="store_true", help="Also remove fresh entries.")
    cache_prune_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                prune_cache(args.max_age_seconds, include_fresh=args.all),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

    manifest_parser = subparsers.add_parser("manifest", help="Validate the workspace manifest.")
    manifest_parser.set_defaults(func=lambda args: print_manifest_report())

    search_plan_parser = subparsers.add_parser("search-plan", help="Build a local search plan from the backlog.")
    search_plan_parser.add_argument("--provider", default="google")
    search_plan_parser.set_defaults(func=lambda args: print(json.dumps(build_search_plan(args.provider), indent=2, ensure_ascii=False)))

    search_open_parser = subparsers.add_parser("search-open", help="Open one search URL from the generated plan.")
    search_open_parser.add_argument("--index", type=int, default=1)
    search_open_parser.add_argument("--provider", default="google")
    search_open_parser.set_defaults(func=lambda args: print(json.dumps(open_search(args.index, args.provider), indent=2, ensure_ascii=False)))

    search_discover_parser = subparsers.add_parser("search-discover", help="Discover unapproved source candidates through configured SearXNG.")
    search_discover_parser.add_argument("--query", default="")
    search_discover_parser.add_argument("--limit", type=int, default=None)
    search_discover_parser.set_defaults(
        func=lambda args: print(json.dumps(discover_sources(args.query, limit=args.limit), indent=2, ensure_ascii=False))
    )

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

    archive_verify_parser = subparsers.add_parser("archive-verify", help="Verify archive paths, inventory, sizes, and SHA-256 hashes.")
    archive_verify_parser.add_argument("--file", default="latest")
    archive_verify_parser.set_defaults(func=print_archive_verify)

    finish_parser = subparsers.add_parser(
        "finish",
        help="Verify, qualify, archive, and integrity-check the completed project.",
    )
    finish_parser.add_argument("--label", default="")
    finish_parser.set_defaults(func=print_finish)

    implement_parser = subparsers.add_parser(
        "implement",
        help="Generate, validate, apply, test, qualify, and archive one approved implementation.",
    )
    implement_parser.add_argument("--task", required=True)
    implement_parser.add_argument("--max-tokens", type=int, default=None)
    implement_parser.add_argument("--retries", type=int, default=0)
    implement_parser.add_argument("--label", default="implementation")
    implement_parser.set_defaults(func=print_implementation)

    decision_parser = subparsers.add_parser("decision-template", help="Print a decision record draft.")
    decision_parser.set_defaults(func=lambda args: print(build_decision_record_draft()))

    decision_write_parser = subparsers.add_parser("decision-draft", help="Write a decision record draft to docs/03-decision-record.md.")
    decision_write_parser.set_defaults(func=lambda args: print(write_decision_record_draft()))

    verify_parser = subparsers.add_parser("verify", help="Run local runtime verification checks.")
    verify_parser.set_defaults(func=lambda args: print_verify())

    verification_plan_parser = subparsers.add_parser("verification-plan", help="Validate decision verification commands against project policy.")
    verification_plan_parser.set_defaults(func=lambda args: print_verification_plan())

    verification_run_parser = subparsers.add_parser("verification-run", help="Run approved decision verification commands.")
    verification_run_parser.add_argument("--continue-on-failure", action="store_true")
    verification_run_parser.set_defaults(func=print_verification_run)

    debate_rounds_parser = subparsers.add_parser("debate-rounds", help="Run multiple debate rounds and a structured decision-maker evaluation.")
    debate_rounds_parser.add_argument("--prompt", required=True)
    debate_rounds_parser.add_argument("--roles", default="")
    debate_rounds_parser.add_argument("--rounds", type=int, default=2)
    debate_rounds_parser.add_argument("--temperature", type=float, default=0.2)
    debate_rounds_parser.add_argument("--max-tokens", type=int, default=None)
    debate_rounds_parser.add_argument("--retries", type=int, default=1)
    debate_rounds_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                run_debate_rounds(
                    args.prompt,
                    roles=[role.strip() for role in args.roles.split(",") if role.strip()] or None,
                    rounds=args.rounds,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    retries=args.retries,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

    debate_status_parser = subparsers.add_parser("debate-status", help="Print a saved multi-round debate session.")
    debate_status_parser.add_argument("--id", default="latest")
    debate_status_parser.set_defaults(
        func=lambda args: print(json.dumps(load_debate_session(args.id), indent=2, ensure_ascii=False))
    )

    debate_resume_parser = subparsers.add_parser(
        "debate-resume", help="Resume a failed debate round or judge stage without repeating completed rounds."
    )
    debate_resume_parser.add_argument("--id", required=True)
    debate_resume_parser.set_defaults(
        func=lambda args: print(json.dumps(resume_debate_rounds(args.id), indent=2, ensure_ascii=False))
    )

    debate_abandon_parser = subparsers.add_parser(
        "debate-abandon", help="Explicitly close a failed or unfinished debate session."
    )
    debate_abandon_parser.add_argument("--id", required=True)
    debate_abandon_parser.add_argument("--reason", required=True)
    debate_abandon_parser.set_defaults(
        func=lambda args: print(
            json.dumps(abandon_debate_rounds(args.id, args.reason), indent=2, ensure_ascii=False)
        )
    )

    patch_plan_parser = subparsers.add_parser("patch-plan", help="Validate a unified diff without changing files.")
    patch_plan_parser.add_argument("--file", required=True)
    patch_plan_parser.set_defaults(
        func=lambda args: print(json.dumps(patch_plan_report(load_patch_file(args.file)), indent=2, ensure_ascii=False))
    )

    patch_apply_parser = subparsers.add_parser("patch-apply", help="Apply a validated unified diff inside editable project roots.")
    patch_apply_parser.add_argument("--file", required=True)
    patch_apply_parser.set_defaults(
        func=lambda args: print(json.dumps(apply_patch_text(load_patch_file(args.file)), indent=2, ensure_ascii=False))
    )

    patch_rollback_parser = subparsers.add_parser("patch-rollback", help="Rollback a recorded patch if files have not changed since.")
    patch_rollback_parser.add_argument("--id", required=True)
    patch_rollback_parser.set_defaults(
        func=lambda args: print(json.dumps(rollback_patch(args.id), indent=2, ensure_ascii=False))
    )

    repair_parser = subparsers.add_parser("repair-run", help="Run a bounded diagnose, patch, verify, and review loop.")
    repair_parser.add_argument("--task", required=True)
    repair_parser.add_argument("--max-attempts", type=int, default=None)
    repair_parser.add_argument("--retries", type=int, default=1)
    repair_parser.set_defaults(
        func=lambda args: print_repair_result(
            run_repair_loop(args.task, max_attempts=args.max_attempts, retries=args.retries)
        )
    )

    repair_status_parser = subparsers.add_parser("repair-status", help="Print one repair session or the latest session.")
    repair_status_parser.add_argument("--id", default="latest")
    repair_status_parser.set_defaults(
        func=lambda args: print(json.dumps(load_repair_session(args.id), indent=2, ensure_ascii=False))
    )

    repair_resume_parser = subparsers.add_parser("repair-resume", help="Safely recover and resume an interrupted repair session.")
    repair_resume_parser.add_argument("--id", required=True)
    repair_resume_parser.add_argument("--retries", type=int, default=1)
    repair_resume_parser.set_defaults(
        func=lambda args: print_repair_result(resume_repair_loop(args.id, retries=args.retries))
    )

    repair_abandon_parser = subparsers.add_parser(
        "repair-abandon", help="Rollback any active patch and explicitly close an unfinished repair session."
    )
    repair_abandon_parser.add_argument("--id", required=True)
    repair_abandon_parser.add_argument("--reason", required=True)
    repair_abandon_parser.set_defaults(
        func=lambda args: print(
            json.dumps(abandon_repair_loop(args.id, args.reason), indent=2, ensure_ascii=False)
        )
    )

    evidence_parser = subparsers.add_parser("evidence", help="List captured search evidence.")
    evidence_parser.set_defaults(func=lambda args: print(evidence_markdown(load_evidence())))

    evidence_check_parser = subparsers.add_parser("evidence-check", help="Validate structured evidence against project policy.")
    evidence_check_parser.set_defaults(func=lambda args: print_evidence_check())

    evidence_rebuild_parser = subparsers.add_parser(
        "evidence-rebuild", help="Rebuild the Markdown evidence view from authoritative JSON."
    )
    evidence_rebuild_parser.set_defaults(
        func=lambda args: print(json.dumps(rebuild_evidence_markdown(), indent=2, ensure_ascii=False))
    )

    claims_parser = subparsers.add_parser("claims", help="Print the structured claim-evidence matrix.")
    claims_parser.set_defaults(func=lambda args: print(claims_markdown()))

    claim_check_parser = subparsers.add_parser("claim-check", help="Validate claims, source links, and challenge resolutions.")
    claim_check_parser.set_defaults(func=lambda args: print_claim_check())

    claim_add_parser = subparsers.add_parser("claim-add", help="Add one evidence-linked knowledge claim.")
    claim_add_parser.add_argument("--claim", required=True)
    claim_add_parser.add_argument("--support-url", action="append", default=[])
    claim_add_parser.add_argument("--challenge-url", action="append", default=[])
    claim_add_parser.add_argument("--status", default="accepted", choices=["accepted", "uncertain", "rejected"])
    claim_add_parser.add_argument("--confidence", default="medium")
    claim_add_parser.add_argument("--resolution", default="")
    claim_add_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                add_claim(
                    claim=args.claim,
                    supporting_urls=args.support_url,
                    challenging_urls=args.challenge_url,
                    status=args.status,
                    confidence=args.confidence,
                    resolution=args.resolution,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

    evidence_fetch_parser = subparsers.add_parser("evidence-fetch", help="Fetch one policy-approved source URL into structured evidence.")
    evidence_fetch_parser.add_argument("--url", required=True)
    evidence_fetch_parser.add_argument("--query", required=True)
    evidence_fetch_parser.add_argument("--why-it-matters", required=True)
    evidence_fetch_parser.add_argument("--recommended-use", required=True)
    evidence_fetch_parser.add_argument("--confidence", default="medium")
    evidence_fetch_parser.set_defaults(
        func=lambda args: print(
            json.dumps(
                fetch_evidence(
                    url=args.url,
                    query=args.query,
                    why_it_matters=args.why_it_matters,
                    recommended_use=args.recommended_use,
                    confidence=args.confidence,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
    )

    evidence_source_check_parser = subparsers.add_parser(
        "evidence-source-check", help="Refetch one fingerprinted evidence URL and detect source changes."
    )
    evidence_source_check_parser.add_argument("--url", required=True)
    evidence_source_check_parser.set_defaults(func=print_evidence_source_check)

    evidence_source_check_all_parser = subparsers.add_parser(
        "evidence-source-check-all", help="Revalidate all fingerprinted evidence sources within the policy limit."
    )
    evidence_source_check_all_parser.add_argument("--limit", type=int, default=None)
    evidence_source_check_all_parser.set_defaults(func=print_evidence_source_check_all)

    evidence_source_refresh_parser = subparsers.add_parser(
        "evidence-source-refresh", help="Refetch and replace one recorded source after reviewing detected changes."
    )
    evidence_source_refresh_parser.add_argument("--url", required=True)
    evidence_source_refresh_parser.set_defaults(
        func=lambda args: print(
            json.dumps(refresh_evidence_source(args.url), indent=2, ensure_ascii=False)
        )
    )

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
    invoke_parser.add_argument("--json", action="store_true")
    invoke_parser.set_defaults(func=print_invoke)

    pipeline_parser = subparsers.add_parser("pipeline", help="Run a small role sequence and save outputs.")
    pipeline_parser.add_argument("--roles", default="planner,designer,architect")
    pipeline_parser.add_argument("--prompt", required=True)
    pipeline_parser.add_argument("--system", default="")
    pipeline_parser.add_argument("--temperature", type=float, default=0.2)
    pipeline_parser.add_argument("--max-tokens", type=int, default=None)
    pipeline_parser.add_argument("--retries", type=int, default=1)
    pipeline_parser.set_defaults(
        func=lambda args: print_pipeline_results(
            run_sequence(
                [role.strip() for role in args.roles.split(",") if role.strip()],
                args.prompt,
                system=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retries=args.retries,
            )
        )
    )

    pipeline_resume_parser = subparsers.add_parser(
        "pipeline-resume", help="Resume a failed pipeline without repeating completed roles."
    )
    pipeline_resume_parser.add_argument("--id", required=True)
    pipeline_resume_parser.set_defaults(func=lambda args: print_pipeline_results(resume_sequence(args.id)))

    pipeline_status_parser = subparsers.add_parser("pipeline-status", help="Print a saved pipeline session.")
    pipeline_status_parser.add_argument("--id", default="latest")
    pipeline_status_parser.set_defaults(
        func=lambda args: print(json.dumps(load_pipeline_session(args.id), indent=2, ensure_ascii=False))
    )

    pipeline_abandon_parser = subparsers.add_parser(
        "pipeline-abandon", help="Explicitly close a failed or unfinished pipeline run."
    )
    pipeline_abandon_parser.add_argument("--id", required=True)
    pipeline_abandon_parser.add_argument("--reason", required=True)
    pipeline_abandon_parser.set_defaults(
        func=lambda args: print(json.dumps(abandon_sequence(args.id, args.reason), indent=2, ensure_ascii=False))
    )

    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()
    try:
        log_event("cli.command.started", command=args.command)
        result = args.func(args)
    except RoleInvocationError as exc:
        log_event("cli.command.failed", command=args.command, error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        print(json.dumps({"diagnostics": exc.diagnostics}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        log_event("cli.command.failed", command=args.command, error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    exit_code = int(result or 0) if result is None or isinstance(result, int) else 0
    if exit_code:
        log_event("cli.command.failed", command=args.command, exit_code=exit_code)
        return exit_code
    log_event("cli.command.completed", command=args.command)
    return 0
