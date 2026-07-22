# Development Goal and Current State

## Goal

Help people using local AI build reliable, working programs easily. The system
must provide a strong harness engineering process that connects specialized AI
roles, verifies knowledge with traceable evidence, enforces decisions before
coding, and repeats implementation, testing, diagnosis, and repair within safe
limits. Cloud AI is an optional escalation path, not a prerequisite.

## User Outcome

A user should be able to describe a program or change, connect local AI models,
and receive a tested result together with the evidence, decisions, diffs, test
results, and remaining risks needed to trust it.

## Implemented

- Project generation and role-to-service routing
- AI invocation, retry, and fallback routing
- Sequential pipelines and structured design debate
- Search planning and structured evidence records
- Policy-driven evidence quality, diversity, freshness, and coverage checks
- Policy-bounded direct URL evidence retrieval with private-network protection
- Decision drafting and coder/reviewer gate enforcement
- Policy-approved verification command execution with bounded output and time
- Policy-bounded unified diff validation, application, backup, and rollback
- Bounded debugger, coder, verification, reviewer, and rollback orchestration
- Checkpoint inspection and conflict-safe repair session recovery
- Exact-input AI response caching and multi-round debate evaluation
- Hash-validated debate verdict handoff into decision drafts and coder briefs
- Evidence-snapshot and accepted-claim freshness checks for debate verdicts
- CLI/HTTP debate-to-decision gate qualification with stale-evidence rejection
- Durable debate round/judge checkpoints and idempotent resume integrated with qualification
- Debate-wide round, elapsed-time, and AI-call budgets with terminal exhaustion
- Auditable abandonment and qualification resolution for superseded debate sessions
- Hash-validated migration of pre-budget debate checkpoints with conservative usage recovery
- Atomic runtime persistence and cross-process session/data locks with dead-owner recovery
- Fail-closed state and scorecard mutation that preserves corrupt originals
- Fail-closed manifest schema and project-bound path validation
- Fail-closed evidence and search-plan loading that preserves corrupt originals
- Latest-checkpoint pointer failure recovery from durable session originals
- Cached pipeline success recovery across the provider-response checkpoint gap
- Cache-key single-flight deduplication for concurrent identical AI requests
- Content-redacted cache observability and lock-safe cache maintenance commands
- Canonical AI cache identity with configuration and credential-rotation invalidation
- Cache result and file-key integrity validation before replay
- Unified unresolved-session overview with progress and safe recovery actions
- Qualification-integrated repair health and rollback-safe auditable abandonment
- Full durable-session history qualification and explicit repair successor handoff
- Direct evidence source fingerprints and content-redacted change revalidation
- Source-change qualification blocking and reviewed evidence refresh with decision invalidation
- Policy-bounded batch source revalidation with complete failure accounting
- Gate-aware deterministic planning, debate, and repair stage execution
- Content-redacted orchestration execution checkpoints and stage-session links
- Qualification-integrated orchestration wrapper lifecycle and auditable abandonment
- Pre-execution child session reservation for hard-interruption recovery
- Hash-validated orchestration resume across the child-creation crash boundary
- Provider-free wrapper reconciliation from durable child state
- Bounded batch reconciliation of terminal orchestration children
- Stage-specific child success enforcement for wrapper completion
- CI-safe orchestration exit codes and nonzero-result audit events
- Reviewer-boundary gate revalidation and stale-approval prevention
- Resume-time saved-approval invalidation and patch rollback
- Coder/reviewer service-identity independence diagnostics
- Optional strict independent-reviewer qualification and repair policy
- Actual fallback/cache coder-reviewer identity enforcement before approval
- Qualification-time durable approved-repair identity revalidation
- SHA-256 provenance binding for actual review identities and verdict
- Strict configured/actual debate-judge independence and provenance validation
- Non-blocking judge diagnostics and strict pre-debate qualification blocking
- Child-first orchestration abandonment with rollback-safe failure handling
- Audit logs, scorecards, manifests, snapshots, rollback, and archives
- English and Korean operating documentation
- Deterministic HTTP integration tests for OpenAI-compatible, Ollama, and fallback routing
- Process-level failed-test, AI patch, retest, and reviewer approval qualification
- Terminal repair budgets for elapsed time, AI calls, and generation tokens
- Consolidated project readiness and executable qualification reporting
- Optional self-hosted SearXNG candidate discovery with separate evidence approval
- Policy-preflighted project archives with secret and symlink exclusions
- Embedded archive SHA-256 inventory and extraction-free integrity verification
- Strict audit-log validation and project-bounded JSON history export
- Append-only SHA-256 audit chaining that anchors legacy history and detects record-level changes
- Qualification-integrated content-redacted audit health
- Qualification-integrated fail-closed scorecard health without damaged-content disclosure
- Authoritative evidence JSON with stale derived-Markdown detection and deterministic rebuild
- Consistent pass/fail process exit contracts across CI-facing checks
- Durable-status-aware process exit contracts for repair and orchestration recovery
- Format-v2 pipeline provenance hashes with canonical historical-checkpoint validation
- Format-v3 debate round and final-result provenance with canonical historical validation
- Format-v2 whole-session repair provenance across save, resume, history, and qualification
- Format-v2 orchestration plan/wrapper provenance with cross-checkpoint binding and canonical historical validation
- Plan-stage role binding and bounded typed orchestration option validation
- Deterministic wrapper-child reservation binding with durable mismatch failure handling
- Stage-specific child-state allowlists and wrapper-child lifecycle consistency validation
- Monotonic wrapper timestamps and status-specific error/abandonment metadata validation
- Re-derived plan semantics and structural role, blocker, gate, service, and command validation
- Deterministic plan blocker and command regeneration from service, gate, tags, and roles
- Canonical terminal wrapper-child existence/status validation in history and qualification
- Terminal wrapper-child task input hash binding across canonical checkpoints
- Terminal wrapper-child role, planning-system, and retry contract validation
- Policy-effective debate round and bounded repair-attempt wrapper-child contracts
- Hash-validated stage-level repair resume with restored time and AI-call budgets
- Redacted per-attempt provider, retry, fallback, timing, and error diagnostics
- Provider-aware live probes that validate configured model availability
- Canonical service identities across adapter aliases and equivalent endpoint URLs
- Shared primary/fallback preflight validation with credential-safe URL diagnostics
- Canonical route deduplication without masking fallback configuration failures
- Explicit malformed service-snapshot handling across diagnostics, invocation, and qualification
- Generated-project role-contract completeness enforcement
- State/service assignment snapshot consistency enforcement
- Cross-platform argument-policy and LF/CRLF patch compatibility fixtures
- Deterministic bilingual task classification and gate-aware role planning
- Run-isolated pipeline checkpoints and idempotent resume from the first unfinished role
- Persisted pipeline role, context, elapsed-time, and cumulative AI-call limits
- Role-output size contracts and CLI/HTTP failed-role resume qualification
- Qualification-integrated pipeline health with explicit auditable abandonment
- Evidence-linked claim matrix, challenge resolution, and decision references
- SHA-256 decision input snapshots that close stale gates after evidence, claim,
  or evidence-policy changes
- End-to-end generated-project lifecycle test from creation through evidence,
  claim validation, decision drafting, and gate opening

## Next Priorities

- Additional discovery providers and richer source validation
- Real-provider debate and repair quality qualification
- Real-provider qualification and finer stage-level idempotency
- Resume, timeout, budget, security, and observability controls

## Definition of Done

- The evidence and decision gates cannot be bypassed by coding roles.
- Generated patches are applied only inside the selected project workspace.
- Declared tests run automatically after each patch.
- Failures produce a focused diagnosis and a bounded repair attempt.
- An independent reviewer decides whether the tested result is acceptable.
- Interrupted runs can resume and all important artifacts remain auditable.
