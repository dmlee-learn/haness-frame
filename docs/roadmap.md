# Harness Engineering Roadmap

## Scope

This roadmap tracks the harness engineering system itself, not a single
generated project.

The target user is someone running one or more local AI models who wants to turn
an idea or change request into a tested program without manually coordinating
planning, coding, review, and repeated fixes.

## Completion Criteria

The core system is complete when it can:

1. Create a runnable project with safe local defaults.
2. Route specialized roles to configured local AI services.
3. Collect and validate evidence before accepting a design decision.
4. Produce a scoped patch from an approved implementation brief.
5. Apply the patch in an isolated workspace and run declared tests.
6. Diagnose failures and repeat patch and test within configured limits.
7. Require independent review before declaring the work complete.
8. Preserve logs, evidence, decisions, diffs, and test results for inspection.
9. Resume interrupted executions without repeating completed stages.
10. Explain the current state, failure reason, and next action in plain language.

## Current State

Implemented:

- Project creation web UI
- Project file generation
- AI service settings in SQLite
- Project role routing
- `workspace/state.json`
- `workspace/services.json`
- `workspace/manifest.json`
- `workspace/scorecard.json`
- `AGENTS.md`, `CLAUDE.md`, `SKILL.md`
- Role-based template generation
- Project runnable `app.py` and `src/harness_app/`
- Policy-approved verification command runner
- Policy-bounded unified diff validation, application, backup, and rollback
- Bounded debugger, coder, verification, reviewer, and rollback loop
- Conflict-safe repair session status and resume flow
- Exact-input AI response cache and multi-round structured debate verdict
- Hash-validated debate verdict handoff into decision and implementation briefs
- Evidence-snapshot and accepted-claim binding for debate verdict freshness
- Process-level HTTP debate-to-decision-to-gate qualification with stale-evidence rejection
- Durable debate round/judge checkpoints, idempotent resume, and qualification health
- Debate-wide round, elapsed-time, and cumulative AI-call budgets preserved across resume
- Auditable debate abandonment for intentionally superseded unfinished sessions
- Hash-validated legacy debate checkpoint migration into global budgets
- Atomic checkpoint replacement, locked shared-data mutation, and PID-owned session operation locks
- Fail-closed mutable JSON updates that preserve malformed state for recovery
- Fail-closed manifest schema and project-bound regular-file validation
- Fail-closed evidence/search-plan loading with mutation preservation
- Latest-pointer interruption recovery from timestamped durable session originals
- Pre-checkpoint pipeline success caching with durable in-flight call reservations
- Cache-key single-flight deduplication for concurrent identical provider calls
- Content-redacted AI cache status and lock-safe stale or malformed entry pruning
- Canonical cache identity with enabled-state and credential-rotation invalidation
- SHA-256 cache result integrity and file-key binding before replay
- Unified content-redacted pipeline, debate, and repair session overview with safe next actions
- Qualification-integrated repair health and rollback-safe auditable abandonment
- Full-history unresolved-session qualification and explicit repair successor handoff
- Normalized source-text fingerprints and content-redacted direct evidence revalidation
- Source-change gate enforcement, policy-bounded revalidation age, and reviewed evidence refresh
- Policy-bounded batch source revalidation with partial-failure continuation
- Gate-aware deterministic task execution across planning, debate, and repair stages
- Content-redacted orchestration execution checkpoints linked to durable stage sessions
- Qualification-integrated orchestration wrapper lifecycle and auditable abandonment
- Pre-execution child session ID reservation for hard-interruption recovery
- Hash-validated orchestration resume before or after child checkpoint creation
- Provider-free wrapper reconciliation from durable child checkpoint state
- Bounded batch reconciliation of terminal orchestration children
- Child-state-aware unresolved-session recovery recommendations
- Stage-specific child success enforcement for orchestration completion
- CI-safe orchestration exit codes and nonzero-result audit events
- Reviewer-boundary decision-gate revalidation with stale-approval rollback
- Resume-time saved-approval invalidation and applied-patch rollback
- Coder/reviewer service-identity diagnostics with non-blocking independence warnings
- Optional strict independent-reviewer policy enforced by qualification and repair
- Actual coder/reviewer invocation identity enforcement across fallback and cache
- Qualification-time durable actual-review identity revalidation
- SHA-256 binding of actual review identities and reviewer verdict
- Optional strict debate-judge independence across configured and actual services
- SHA-256 judge provenance validation in decision handoff and qualification
- Non-blocking configured judge diagnostics and strict pre-debate qualification
- Provider-aware endpoint probes with configured-model availability validation
- Canonical service identities resistant to provider-alias and equivalent-URL bypasses
- Shared preflight validation for primary/fallback URL safety and enabled state
- Canonical route deduplication for endpoint probes and fallback execution
- Content-redacted malformed service-snapshot diagnostics across check, invoke, and qualification
- Project role-contract completeness checks for generated service snapshots
- Cross-snapshot role-assignment consistency validation
- Child-first orchestration abandonment with rollback-safe failure handling
- Policy-bounded direct URL evidence retrieval with private-network protection
- Deterministic HTTP qualification for OpenAI-compatible, Ollama, and fallback routing
- Process-level failed-test, AI patch, retest, and independent approval fixture
- Source timestamp invalidation for reliable same-size Python patch verification
- Repair elapsed-time, AI-call, and per-call generation-token budgets
- Snapshot-history-preserving restore and project-bounded evidence draft input
- Empty, duplicate, unknown, and backward role-sequence validation
- Consolidated ready/qualified report with optional live probes and test execution
- Policy-bounded self-hosted SearXNG candidate discovery separated from evidence approval
- Preflighted archive export with secret, symlink, count, and size protections
- Embedded archive SHA-256 inventory and extraction-free integrity verification
- Strict audit-log validation and project-bounded JSON history export
- Append-only SHA-256 audit chaining with legacy-prefix anchoring and qualification enforcement
- Content-redacted audit health as a qualification readiness gate
- Fail-closed, content-redacted scorecard health as a qualification readiness gate
- Authoritative evidence JSON with stale Markdown detection and deterministic recovery
- Consistent nonzero CLI exit contracts for every CI-facing validation command
- Durable-status-aware exit contracts for repair and orchestration recovery commands
- Format-v2 pipeline result provenance hashes enforced across history and qualification scans
- Format-v3 debate round provenance and full final-result hashes enforced across historical scans
- Format-v2 whole-session repair provenance enforced on save, resume, history, and qualification
- Format-v2 plan and wrapper provenance, cross-checkpoint binding, and canonical history validation
- Plan-stage role binding and bounded typed orchestration option validation
- Deterministic wrapper-child reservation binding and mismatched-result failure checkpointing
- Stage-specific child status allowlists and wrapper-child lifecycle consistency validation
- Monotonic timezone-aware wrapper timestamps and status-specific error/abandonment invariants
- Re-derived plan classification/roles and structural role, blocker, gate, and command validation
- Deterministic blocker and command regeneration from service/gate/task plan inputs
- Canonical terminal wrapper-child existence and status validation in history and qualification
- Cross-checkpoint terminal wrapper-child task input hash binding
- Terminal wrapper-child role, planning-system, and retry-contract binding
- Effective policy-clamped debate rounds and bounded repair-attempt child contracts
- Hash-validated stage-level repair resume with restored execution budgets
- Redacted per-attempt provider, retry, fallback, timing, and error diagnostics
- Cross-platform argument-policy and LF/CRLF patch compatibility fixtures
- Deterministic bilingual task classification and gate-aware role planning
- Run-isolated pipeline checkpoints with forward-only, idempotent resume
- Persisted pipeline role, context, elapsed-time, and AI-call budgets
- Policy-bounded role-output contracts and process-level HTTP resume qualification
- Qualification-integrated pipeline health and explicit auditable abandonment
- Evidence-linked claim matrix with challenge resolution and decision references
- SHA-256 decision input snapshots that invalidate stale approvals after evidence,
  claim, or evidence-policy changes
- Generated-project lifecycle fixture covering creation, evidence capture, claim
  validation, decision drafting, and decision-gate opening

## Phase 1 Priority

1. Project-local AI execution using `workspace/services.json`
2. Prompt assembly per role
3. Provider adapters for `openai_compatible`, `ollama`, `anthropic`, `codex`
4. Response parsing and fallback handling
5. Minimal smoke tests for AI calls

## Phase 2 Priority

1. Role pipeline orchestration
2. Search and evidence capture
3. Decision gate enforcement
4. Scorecard updates
5. Execution logs

Current partial implementation:

- Project-local `invoke` command
- Sequential `pipeline` command with run-isolated per-role checkpoints and resume
- Fallback execution for dead role services

## Phase 3 Priority

1. Retry and timeout policy
2. Fallback model selection
3. Snapshot and rollback support
4. Manifest validation
5. More stable project settings UI

## Phase 4 Priority

1. Additional search-provider adapters beyond self-hosted SearXNG
2. Debate and review loop automation
3. Multi-language growth
4. Tool-call support
5. Project archival and backup automation

## Phase 5 Priority

1. Real-provider repair loop qualification
2. Real-provider end-to-end qualification using the process fixture

## Nice To Have

- Project progress dashboard
- Better provider-specific diagnostics
- Batch project generation

## Operating Rule

Do not expand the orchestration layer until Phase 1 can actually call a model
using the project-local service snapshot.
