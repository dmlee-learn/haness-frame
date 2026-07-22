# Test Project Manual

## Purpose

Use a generated project to validate the complete harness flow: project creation, role routing, evidence capture, debate, decision approval, implementation handoff, and verification.

## Create a Project

```powershell
python .\src\haness_frame.py create-project --project "harness-test" "Build a small test application"
cd .\projects\harness-test
```

## Validate the Runtime

```powershell
python app.py check --no-probe
python app.py check
python app.py live-check --role planner
python app.py qualify
python app.py qualify --probe-services --run-verification
python app.py runs --unresolved
python app.py summary
python app.py role-plan --task "Fix the failing import and add a regression test"
python app.py orchestrate --stage planning --task "Design the requested change"
python app.py orchestrate --stage debate --task "Compare the implementation options"
python app.py orchestrate --stage repair --task "Fix the approved implementation"
python app.py orchestrate-status --id latest
python app.py orchestrate-resume --id EXECUTION_ID
python app.py orchestrate-reconcile --id EXECUTION_ID
python app.py orchestrate-reconcile-all --limit 100
python app.py orchestrate-abandon --id EXECUTION_ID --reason "Superseded orchestration"
python app.py search-plan
python app.py search-discover
python app.py evidence-draft
python app.py evidence-gaps
python app.py evidence-check
python app.py evidence-rebuild
python app.py claim-add --claim "The selected API remains compatible" --support-url "https://example.com/source"
python app.py claim-check
python app.py claims
python app.py evidence-fetch --url "https://example.com/source" --query "source question" --why-it-matters "Design constraint" --recommended-use "Use in the decision record"
python app.py evidence-source-check --url "https://example.com/source"
python app.py evidence-source-check-all
python app.py evidence-source-refresh --url "https://example.com/source"
python app.py gate
python app.py verify
python app.py verification-plan
python app.py verification-run
python app.py patch-plan --file workspace/candidate.diff
python app.py patch-apply --file workspace/candidate.diff
python app.py archive --label "verified"
python app.py archive-verify
python app.py audit-check
python app.py audit-export
python app.py ai-cache-status
python app.py ai-cache-prune --max-age-seconds 86400
python app.py repair-run --task "Fix the failing implementation"
python app.py repair-status
python app.py repair-resume --id SESSION_ID
python app.py repair-abandon --id SESSION_ID --reason "Superseded repair"
python app.py invoke --role planner --prompt "Summarize the project state" --json
python app.py debate-rounds --prompt "Compare the implementation options" --rounds 2
python app.py debate-status --id latest
python app.py debate-resume --id DEBATE_ID
python app.py debate-abandon --id DEBATE_ID --reason "Superseded by corrected requirements"
python app.py pipeline-status --id latest
python app.py pipeline-resume --id RUN_ID
python app.py pipeline-abandon --id RUN_ID --reason "Superseded run"
```

Start with `check --no-probe` to validate provider types, URLs, model names,
enabled state, and required API-key environment variables without contacting a
service. Run `check` when the configured providers are running. It probes each
unique shared endpoint once, reports failures as structured JSON, updates the
scorecard and audit log, and returns a nonzero exit code when configuration or
connectivity is invalid. Use `--timeout SECONDS` to change the per-probe timeout.
HTTP(S) URL structure and configured fallback services are validated too;
embedded URL credentials, queries, and fragments are rejected. Invocation uses
the same checks before calling primary or fallback services.
Provider aliases and equivalent URL spellings for one canonical route are probed
once and are not retried as fallback. Different validation states are still
reported separately.
Malformed `services.json` content and invalid service-map shapes produce explicit,
content-redacted configuration issues. The cause is retained by `qualify` and
direct role invocation rather than collapsing to an unassigned-role error.
Use `live-check --role ROLE` as an explicit environment acceptance test. It
first probes every configured service and then performs one small role call.
The result reports service identity, fallback use, attempt count, response
length, and SHA-256 without exposing the fixed probe prompt or response body.
It exits nonzero when configuration, model discovery, connectivity, or the
generation call fails. This command is intentionally excluded from the default
offline test suite.
Generation requests use a 120-second timeout by default. A service can override
this with `request_timeout_seconds` between 1 and 600 in
`workspace/services.json`. Invalid values fail configuration validation before
any network request.
The generated state and service snapshots define the expected project roles.
Missing `role_services` keys are listed as unassigned and block qualification.
Minimal standalone fixtures with no declared role contract remain partial by design.
For declared assignments, the state snapshot, service assignment map, and each
configured service `name` must agree. Mismatches are reported by role without
echoing the configured service values.
The report compares coder and reviewer by provider, endpoint, and model. An
identical execution identity produces a non-blocking independence warning in
both `check` and `qualify`; use a distinct model or endpoint for stronger review.
Set `require_independent_reviewer_service` to `true` in `repair-policy.json` to
enforce this. Strict mode blocks qualification and repair start/resume until the
coder and reviewer execution identities differ.
Repair records the actual service identity used by coder and reviewer, including
fallback and cached responses. In strict mode, identical actual identities block
final approval and route the applied patch through rollback.
OpenAI-compatible provider aliases and equivalent endpoint URL spellings are
canonicalized, so changing an adapter label, default port, or trailing slash does
not create false independence.
Strict qualification independently checks the identities stored in an approved
repair checkpoint. Shared or incomplete durable identity evidence blocks the
project even when the session status says `approved`.
Each approved attempt hashes the coder identity, reviewer identity, and reviewer
verdict into `review_provenance_sha256`. Strict qualification rejects a missing
hash or any post-approval identity/verdict change.
Set `require_independent_debate_judge_service` to `true` in
`orchestration-policy.json` to enforce a distinct decision-maker judge. Both the
configured identity and actual fallback/cache identity must differ from every
participant. `judge_provenance_sha256` binds those identities to the verdict and
evidence digest for decision handoff and qualification.
`check` emits a non-blocking warning when the configured judge shares an
identity with a participant. Strict qualification blocks before a debate starts
and, for an existing session, checks only its selected participant roles before
revalidating actual execution identities and provenance.

`qualify` writes one consolidated compilation, manifest, service, evidence, and
decision-gate report. It returns `ready` when those checks pass without running
tests. `--run-verification` executes the policy-approved commands and is required
for `qualified`; `--probe-services` also checks live endpoints and confirms the
configured model in standard OpenAI-compatible or Ollama model-list responses.
Nonstandard response formats retain the HTTP connectivity result. Reports are kept
under `workspace/qualifications/`.
The manifest must be a regular JSON-object file with project metadata and a
non-empty, duplicate-free list of regular files inside the project root. Unsafe,
missing, directory, or symlink entries fail qualification; `manifest` also exits
nonzero when this report is invalid.

`runs` summarizes durable pipeline, debate, and repair sessions without prompt
or AI output content. Add `--unresolved` to focus on sessions needing attention;
the report provides progress, a bounded failure reason, and a safe next command.

An unresolved latest repair blocks qualification. `repair-abandon` records why
superseded work was closed and first rolls back any active patch. If later user
changes prevent rollback, the session remains `rollback_blocked`. Successful
repairs cannot be abandoned, and abandoned repairs cannot resume.
Qualification scans all durable pipeline, debate, and repair sessions, not only
the latest pointers. A later success cannot hide older failed, running, or
corrupt work. A repair that successfully hands remaining attempts to a new
session is marked `superseded` with its successor ID and is resolved.

Fill `research/search-evidence-draft.md`, commit it with `python app.py evidence-commit`, and generate the decision draft with `python app.py decision-draft`. The coder and reviewer remain blocked until the evidence and decision requirements pass.

Before executing project tests, add the exact approved commands to
`workspace/verification-policy.json`. `verification-plan` reports rejected
commands without executing them. `verification-run` requires an open decision
gate and writes complete results to `workspace/verifications/latest.json`.
Policy matching compares parsed arguments, preserves quoted whitespace, and
rejects shell operators and control characters. Bare Python launchers use the
current runtime; explicit interpreter paths remain unchanged. Quoted paths with
spaces are supported on Windows and POSIX.

Place an AI-generated unified diff inside the project, validate it with
`patch-plan`, and apply it with `patch-apply`. Editable roots and patch limits
come from `workspace/repair-policy.json`. Each successful patch returns a patch
ID. Use `python app.py patch-rollback --id PATCH_ID` only when rollback reports
no later file changes.
Patch headers may use slash or Windows-style separators. LF and CRLF diffs are
accepted while the target file's existing newline convention is preserved.

Use `archive` to export an inspectable project ZIP. The runtime preflights file
count, individual size, and total size using `workspace/archive-policy.json`.
Symlinks, previous archives, VCS metadata, bytecode, `.env`, key, and certificate
files are excluded by default. Policy failure does not leave a partial ZIP.
Each archive embeds a SHA-256 inventory. Run `archive-verify` for the newest
archive, or add `--file PATH`, to detect missing, added, changed, duplicate, or
unsafe-path members without extracting the ZIP.

Run `audit-check` to validate every JSONL record, timestamp, and SHA-256 record chain.
The first version-2 event anchors existing legacy records; subsequent events detect
valid-JSON modification, insertion, deletion, and reordering. The chain provides
consistency detection, not cryptographic signing against a writer who can recompute it. Run
`audit-export`, optionally with `--filename NAME.json`, to preserve the complete
history, event counts, and validation findings in `workspace/reports/`.
Qualification includes only the audit summary and blocks readiness for malformed
rows, missing required fields, or invalid timestamps. It does not embed event
records in the qualification artifact.
Qualification also validates the scorecard root and boolean checks. Invalid
scorecards remain untouched and are reported without exposing their contents.

`repair-run` performs the bounded modification loop. The debugger must return
JSON with `diagnosis`, `files`, and `strategy`; the coder must return one fenced
unified diff; and the reviewer must return JSON with `approved`, `reason`, and
`risks`. Attempts and full outputs are stored under `workspace/repairs/`.
Use `repair-status` to inspect the latest checkpoint. `repair-resume` validates
saved patch hashes and resumes from the last durable debugger, diff, patch,
verification, or reviewer stage without repeating completed AI calls. Restored
time and AI-call usage still count toward the same limits. Failed or rejected
work is rolled back before a linked session receives the remaining attempts. A
file conflict blocks resumption instead of overwriting later user changes.
Format-v2 repair sessions refresh a canonical whole-session SHA-256 at every
durable save. It covers task metadata, budgets, attempts, verification, patch
and rollback records, actual service identities, and reviewer data. Canonical
loading validates identity, status, attempt sequence, approved review provenance,
and the hash across resume, historical `runs`, and qualification. Format v1
remains readable.

### One-Command Implementation And Finish

After the decision gate is open and `verification-plan` is approved, run:

```powershell
.\run.ps1 implement --task "Implement the approved change"
```

This command generates and normalizes a coder diff, validates editable paths,
creates a snapshot, applies the patch, runs approved tests and qualification,
rolls back a failed implementation, and creates and verifies an archive after
success. For an implementation that is already applied, run only:

```powershell
.\run.ps1 finish
```

`workspace/repair-policy.json` also defines `max_elapsed_seconds`,
`max_ai_calls`, and `ai_max_tokens`. Exhausting one of these limits records a
terminal `budget_exhausted` session. An active patch is safely rolled back before
the loop stops.

`debate-rounds` passes each round's positions into the next round and requires a
decision-maker JSON verdict containing the decision, rationale, agreements,
disagreements, risks, confidence, implementation brief, and proposed verification
commands. The verdict is stored with a canonical SHA-256. `decision-draft`
validates that hash and uses the verdict in the accepted decision and coder
brief. Tampering blocks draft generation. Proposed commands still require an
exact match in `workspace/verification-policy.json`. Identical successful AI
calls may be reused from `workspace/cache/ai/` according to the repair policy.
The debate report binds the verdict to the current evidence, claims, and policy
digest. Its `claim_ids` must reference accepted structured claims and, when the
claim matrix is required and valid, must include every accepted claim. Any
knowledge change makes the verdict stale; rerun `debate-rounds` before drafting.
Each multi-round debate has a durable session. Use `debate-status` to inspect the
current round, linked pipeline, completed rounds, and judge stage. `debate-resume`
continues the failed pipeline or retries only the judge without repeating
completed rounds. If evidence changes before judgment, the session becomes
terminal `stale`. Unresolved or corrupt latest debate sessions block `qualify`.
The same orchestration policy limits the entire debate with
`max_debate_rounds`, `max_debate_elapsed_seconds`, and `max_debate_ai_calls`.
Each round reserves all role calls before execution, and each judge attempt
reserves one call. Saved usage is restored by `debate-resume`; exhaustion is a
terminal `budget_exhausted` state and blocks `qualify`.
Format-v3 debate sessions hash every round's complete role-output provenance.
Format-v2 final reports hash the verdict, rounds, actual service independence,
participant identities, and judge identity as one result. Resume, historical
`runs`, and qualification use canonical validation, while existing format-v2
sessions remain compatible.
Use `debate-abandon` with a reason when a failed, stale, or unfinished session
has been intentionally superseded. The abandonment is audit logged, resolves
qualification health, cannot be resumed, and does not masquerade as completion.
Older hash-valid debate checkpoints without debate-wide budget fields are
migrated on load. Completed rounds and an attempted judge are charged to the
restored budget; malformed or hash-mismatched legacy checkpoints are rejected.
Runtime checkpoints use flushed same-directory temporary files and atomic
replacement under per-file locks. Audit append, scorecard updates, evidence, and
claim mutations are serialized. Resume and abandon commands for the same
pipeline, debate, or repair session cannot execute concurrently. A live owner
produces an `already active` error; a lock left by a dead process is recovered.
Mutable JSON updates fail closed when an existing file is malformed or has a
non-object root. The error reports only path and parse location, and the original
state or scorecard bytes remain untouched for recovery.
If the duplicated `latest` checkpoint is missing or older because the process
stopped between the two atomic writes, the newest durable session original is
selected by `updated_at`. Qualification therefore still reports interrupted
work instead of treating it as not started.
Each pipeline role records its in-flight call reservation before invocation and
caches a contract-valid provider success before the role checkpoint. A crash in
that interval is resumed from cache without another provider call or AI-call
budget charge. Output rejected by the size contract is not cached. Concurrent
requests for the same role, prompt, routing, and generation settings are
single-flight: only the lock owner calls the provider, and waiters reuse the
saved success while preserving their own pipeline budget accounting.
Cache format v2 canonicalizes provider aliases and equivalent URLs. Changes to
enabled state, configuration validity, or the API-key value invalidate reuse.
The credential fingerprint is used only while deriving the final cache key and
is not persisted in cache content or audit events.
Every entry stores `result_sha256`, binding the file key, role, response,
service metadata, and diagnostics. Modified or renamed entries are rejected as
invalid and can be removed with the normal prune command.
Use `ai-cache-status` to inspect fresh, stale, and malformed entry counts and
total bytes without exposing prompts or response content. `ai-cache-prune`
removes stale and malformed entries with cache-key locking; `--all` also clears
fresh entries.

Evidence requirements are configured in `workspace/evidence-policy.json`.
Run `evidence-check` before drafting a decision to inspect record count,
distinct URLs, confidence, timestamps, freshness, duplicates, and optional
search coverage.
The structured JSON file is authoritative and is committed before its Markdown
view. A stale existing view makes `evidence-check` return nonzero; run
`evidence-rebuild` to regenerate it after an interrupted write.
For CI, `gate`, `verify`, `claim-check`, `evidence-check`, `verification-plan`,
`verification-run`, `archive-verify`, `audit-check`, `manifest`, and `check`
return `0` only when the reported condition passes and `1` when it fails.
`search-evidence.json` must be a JSON list of object records and `search-plan.json`
must be a JSON object. Malformed or wrong-root files close the gate and fail
qualification with redacted path/location issues. Add, refresh, and draft-commit
mutations preserve the damaged original instead of resetting it.

New projects require a claim-evidence matrix. Use `claim-add` only with URLs
already present in structured evidence. Accepted claims need supporting sources;
challenging sources need a substantive `--resolution`; and the decision record
must cite each accepted claim ID or its complete text. Use `claim-check` before
opening the gate. Migrated existing projects keep `require_claim_matrix: false`
until the matrix is populated and explicitly enabled.

New projects also set `require_decision_snapshot: true`. `decision-draft`
records a SHA-256 digest of the current evidence, claims, and evidence policy.
Changing any of those inputs closes the coder and reviewer gate until the
decision is reviewed and regenerated. Migrated projects keep this setting
disabled until the existing decision workflow is ready for strict invalidation.

Use `evidence-fetch` only with a direct source URL, not a search-results page.
It extracts a bounded title and text excerpt and commits the result through the
same evidence store. `workspace/evidence-policy.json` controls whether fetching
is enabled, timeout, maximum bytes, excerpt length, accepted content types,
optional allowed domains, and private-network access. Private and loopback
destinations are blocked by default, including after redirects.
Direct fetches store a SHA-256 fingerprint of normalized visible text. Run
`evidence-source-check --url URL` to detect changed content or redirect targets;
it exits nonzero on change and stores hashes and metadata, never the fetched
body. New projects require fingerprints for `direct_url` records. Migrated
projects can enable `require_source_fingerprint` after recapturing those records.
Detected source changes block evidence policy and qualification. After review,
`evidence-source-refresh` replaces the record and verification atomically; the
new evidence digest keeps the decision gate closed until the decision is
regenerated. Enable `require_source_revalidation` and configure
`max_source_verification_age_days` when periodic checks must be mandatory.
`evidence-source-check-all` validates all fingerprinted HTTP sources within
`max_source_checks_per_run`. It continues after per-source failures and returns
nonzero if any source changed, failed, or was skipped by the limit.

Automatic candidate discovery is optional and disabled by default. Configure a
self-hosted SearXNG endpoint in `workspace/search-policy.json`, set `enabled` to
true, then run `search-discover` for the current plan or add `--query`. Results
are unapproved candidates only. Fetch and validate a direct result URL before it
can contribute to the evidence gate.

## AI Workflow

Run a single role with `invoke`, a sequence with `pipeline`, or the design roles
with `debate`. Add `--json` to `invoke` to inspect redacted primary/fallback
attempts, durations, HTTP status, retryability, and error categories. Pipeline
execution files and cache hits preserve these diagnostics. Prompts, response
bodies, credentials, URL user information, and query strings are excluded.
Configure role-to-service assignments before using real AI providers.

Each pipeline receives a run ID and stores a durable session plus per-role
outputs under `workspace/executions/runs/`. Inspect it with `pipeline-status`.
If a role fails, `pipeline-resume` rebuilds context from saved outputs and starts
at the first unfinished role. It does not repeat completed AI calls, and resuming
a completed pipeline returns the recorded results without invoking a provider.
Format-v2 pipeline checkpoints hash each complete role-result provenance record,
including service identity, diagnostics, content, and context metadata. Loading
also validates session identity, inputs, status, sequence, and completed result
count. Historical `runs` and qualification scans use the same validation, while
format-v1 checkpoints retain compatible content-hash validation.
`workspace/orchestration-policy.json` limits roles, prompt and system length,
carried context, elapsed time, and cumulative AI calls. Limits and usage are
saved in the session. AI calls are reserved before provider invocation, so a
crash cannot restore spent capacity. Budget exhaustion is terminal, and older
role outputs are compacted before context exceeds its configured maximum.
`min_output_chars` and `max_output_chars` prevent non-empty but unusable or
unbounded responses from reaching the next role. A rejected output consumes its
reserved AI call and leaves the same role pending for an explicit resume.
`qualify` checks both policy validity and the latest checkpoint. Unresolved or
corrupt runs block readiness. When a run is intentionally superseded, close it
with `pipeline-abandon` and a reason; this records an auditable resolved state
without pretending that the run completed.

`role-plan` uses deterministic English and Korean task signals to recommend a
forward-only role sequence. It reports missing or disabled services and keeps
coder/reviewer blocked when the decision gate is closed. It writes JSON plans to
`workspace/orchestration/` but does not invoke AI or execute the suggested work.
Use `orchestrate` to execute one validated stage from that plan. `planning` runs
the forward pipeline; `debate` runs planning participants and a separate
decision-maker judge; `repair` runs debugger, coder, verification, and reviewer.
Service and decision-gate blockers fail before provider calls, while each stage
retains its underlying durable checkpoints, budgets, resume, and rollback rules.
The wrapper stores a content-redacted execution checkpoint under
`workspace/orchestration/executions/`, linking the plan ID and task hash to the
underlying session. Inspect successful or failed wrappers with
`orchestrate-status` without exposing task or AI output content.
Format-v2 plans and wrappers hash their complete stored provenance. A wrapper
binds both the plan hash and redacted task hash to the original plan. The canonical loader also checks
stage, child identity, and terminal status consistency. `runs` and qualification
apply that loader to historical wrappers, so tampering with a completed wrapper
turns it into an `invalid_checkpoint` that requires attention.
Plan loading re-derives task tags and recommended/planning roles from the task.
It validates role and service snapshots, blocker summaries, invocability flags,
decision-gate structure, and bounded command templates even after hashes are recomputed.
Blockers are recalculated from service assignment/enabled flags and gate state;
the exact command sequence is regenerated from task tags and planning roles.
The wrapper role order must equal the roles derived from the saved plan and
stage. Round, retry, and repair-attempt options use a bounded typed schema that
is checked before creating a plan and on every format-v2 wrapper load.
The child pipeline, debate, or repair ID is reserved before stage execution, so
a hard interruption preserves the recovery target in the wrapper checkpoint.
That ID is derived deterministically from the wrapper ID and task hash. Loading
rejects a different link even after hash recomputation, while a stage engine
that returns another ID leaves a canonical failed wrapper for recovery.
Child status is limited to states emitted by the corresponding durable engine,
and wrapper-child lifecycle pairs must be consistent. For example, a running
wrapper cannot claim a completed child and an abandoned wrapper cannot retain
an active child link.
Wrapper lifecycle timestamps must include a timezone and remain monotonic.
Running/completed wrappers have no error, failed wrappers require one, and an
abandoned wrapper requires a bounded reason and in-range abandonment timestamp.
`orchestrate-resume` verifies the stored plan and task hash, resumes an existing
child checkpoint, or starts the stage with its reserved ID when the child was
not created yet. Repeating it after completion performs no provider work.
Use `orchestrate-reconcile` to copy terminal or active child state into the
wrapper without continuing the child or calling a provider. This repairs the
checkpoint gap after a child finished but before its wrapper was updated.
`orchestrate-reconcile-all` performs the same provider-free repair in a bounded
batch and skips wrappers whose children are active or absent.
Wrapper completion requires a successful child status: completed planning or
debate, or an approved/already-verified repair. Terminal non-success results
remain failed even when the child command returned normally.
`orchestrate`, `orchestrate-resume`, and `orchestrate-reconcile` exit with `0`
only when the wrapper is completed. A persisted non-success result exits with
`2`; invocation and validation exceptions exit with `1`. `repair-run` and
`repair-resume` return `0` only for `approved` or `already_verified`, and `2`
for durable unsuccessful terminal states. Reconcile-all returns `1` if any
wrapper inspection fails.
Repair checks the current decision gate before reviewer work and immediately
before final approval. If evidence, claims, or the decision changed during the
attempt, stale approval is blocked and an applied patch is rolled back according
to policy.
A saved approved verdict is not trusted blindly after interruption. Resume
revalidates it, marks stale approval explicitly, and rolls back its applied
patch before returning the gate failure.
Unresolved wrappers are included in `runs --unresolved`, which selects a safe
reconcile, resume, or abandon action from the child checkpoint, and qualification
history. Use `orchestrate-abandon` with a reason for superseded wrappers. It
abandons an existing linked pipeline, debate, or repair session first. If
child cleanup or repair rollback fails, the wrapper stays unresolved.
History validation follows terminal links: a completed wrapper requires an
existing canonical child checkpoint. An abandoned wrapper may omit its child
only when linked as `not_started`, and otherwise its stored child status must
equal the canonical checkpoint status.
The wrapper task hash must equal the canonical pipeline/debate prompt hash or
repair task hash. A canonical child created for another task cannot satisfy a
terminal wrapper even when placed at the expected path.
Pipeline/debate child roles must equal the wrapper role order. Planning also
requires the fixed evidence-aware system prompt, and pipeline/debate retry
options must match the saved wrapper option.
Debate rounds are clamped by policy before writing either checkpoint, and the
terminal child count must match the effective wrapper count. Repair attempt
limits must be valid and cannot exceed an explicit wrapper request.

## Current Boundary

The runtime creates search plans, optionally discovers unapproved candidates
through self-hosted SearXNG, and safely ingests explicitly approved source URLs.
Safe patch handling and bounded AI repair orchestration are implemented.
Real-provider end-to-end qualification and additional discovery providers remain
priorities.
