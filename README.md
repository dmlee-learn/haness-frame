# haness-frame

Korean documentation: [README.ko.md](README.ko.md)

Local-first harness engineering framework for building reliable software with AI.

## Goal

Help local AI users build working programs easily through a robust engineering
process. The harness turns a request into evidence-backed design decisions,
focused implementation, executable tests, review, and bounded repair loops.

The project is successful when a user can connect local AI services and move
from an idea to a verified program without asking one model to plan, code, test,
and judge its own work in a single pass.

Use separate local models for separate responsibilities:

```text
Planner / Reviewer:
  vLLM NVIDIA-Nemotron-Nano-9B-v2

Coder / Patch Generator:
  vLLM Qwen2.5-Coder-14B-Instruct-AWQ

Fallback / Tool-call:
  vLLM Qwen3-8B-AWQ

Escalation:
  Gemini or another cloud model
```

The key rule is strict role separation. The planner summarizes, decomposes,
and reviews. The coder generates concrete patches.

Core principles:

- Local AI is the default; cloud escalation is optional.
- Evidence and explicit decisions precede implementation.
- Every implementation must have executable verification commands.
- Failed verification enters a bounded diagnose, patch, and retest loop.
- The harness preserves user work and records decisions, attempts, and results.
- Safe defaults and clear next actions keep the workflow approachable.

## Files

```text
config/harness.yaml        Model endpoints and role policy
config/roles.yaml          Role definitions for design discussion
config/design_loop.yaml    Structured research/debate/decision stages
docs/architecture.md       Harness design and loop
docs/design-discussion-framework.md  Design discussion workflow
docs/roadmap.md           Implementation priorities and phases
docs/ko-test-project-manual.md       Korean test project manual
docs/test-project-manual.en.md       English test project manual
docs/test-project-manual.ko.md       Korean test project manual (UTF-8)
docs/prompts.md            Prompt contracts per role
scripts/check-services.ps1 Windows/WSL service check
scripts/start-vllm-*.ps1   Start planner/coder/fallback vLLM profiles
src/haness_frame.py        Thin CLI entrypoint
src/haness_frame_app/      Role-based implementation modules
```

## Quick Check

From this directory:

```powershell
python .\src\haness_frame.py check
python .\src\haness_frame.py show-config
python .\src\haness_frame.py roles
python .\src\haness_frame.py design-loop
python .\src\haness_frame.py init-db
python .\src\haness_frame.py services
```

Development and testing notes are maintained in both languages:

- `localdoc/development-goal-summary.en.md`
- `localdoc/development-goal-summary.ko.md`
- `localdoc/testing-process.en.md`
- `localdoc/testing-process.ko.md`

## Harness Runtime

Inside a generated project, use:

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
python app.py evidence-commit
python app.py evidence-check
python app.py evidence-rebuild
python app.py claim-add --claim "The selected API remains compatible" --support-url "https://example.com/source"
python app.py claim-check
python app.py claims
python app.py evidence-fetch --url "https://example.com/source" --query "source question" --why-it-matters "Design constraint" --recommended-use "Use in the decision record"
python app.py evidence-source-check --url "https://example.com/source"
python app.py evidence-source-check-all
python app.py evidence-source-refresh --url "https://example.com/source"
python app.py decision-draft
python app.py verify
python app.py verification-plan
python app.py verification-run
python app.py implement --task "Implement the approved change"
python app.py finish
python app.py patch-plan --file workspace/candidate.diff
python app.py patch-apply --file workspace/candidate.diff
python app.py patch-rollback --id PATCH_ID
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

`check --no-probe` validates provider type, URL, model, enabled state, and any
required API-key environment variable without making a network request. `check`
also probes each unique configured endpoint (`/models` for OpenAI-compatible
services and `/api/tags` for Ollama). Roles sharing one service are grouped into
one probe. Service URLs must use HTTP(S), include a host, and exclude embedded
credentials, queries, and fragments. Configured fallback services are included,
and invocation applies the same validation before calling primary or fallback.
`live-check` is the opt-in acceptance check for a running local provider. It
probes all configured services and makes one bounded role call. Its JSON report
contains only response length and SHA-256, never the prompt or response body.
Provider generation requests default to 120 seconds. Set
`request_timeout_seconds` on a role or fallback service in
`workspace/services.json` to an integer from 1 through 600 when a model needs a
different limit.
Equivalent canonical routes are probed once and are not retried as fallback;
different validation states remain separate so a disabled fallback cannot be
hidden by a valid primary.
Malformed JSON and invalid `role_services`/`fallback_service` shapes are reported
as content-redacted configuration issues instead of being treated as an empty
service set. Qualification and direct invocation preserve the same cause.
Generated projects also declare their expected roles in the service/state
snapshots. A missing `role_services` key for any declared role is reported as
unassigned and blocks qualification; standalone minimal fixtures without a role
contract can still configure only the roles they exercise.
When assignment metadata exists, the state snapshot, service assignment map, and
configured service `name` must agree for each role. Stale or malformed mappings
produce role-scoped configuration issues without printing service values.
The command prints structured failure reasons, updates the runtime
scorecard and audit log, and exits nonzero when any service is invalid or
unreachable.
The report also compares coder and reviewer execution identities. Sharing the
same provider endpoint and model produces a non-blocking independence warning
even when service names differ; a distinct endpoint or model clears it.
Set `require_independent_reviewer_service` to `true` in
`workspace/repair-policy.json` to make this mandatory. Strict mode blocks
qualification and repair start/resume until coder and reviewer are distinct.
Strict mode also records the actual provider endpoint and model returned by each
coder/reviewer invocation. Final approval is blocked and the patch is rolled
back if fallback or cached execution makes those actual identities identical.
OpenAI-compatible adapter aliases and equivalent URL spellings, including
default ports and trailing slashes, are canonicalized before comparison.
Qualification revalidates the durable identities in every latest approved repair
under strict mode. Shared, missing, or incomplete actual identity evidence keeps
the project blocked even if the checkpoint claims `approved`.
Approved attempts store `review_provenance_sha256`, binding coder identity,
reviewer identity, and the reviewer verdict. Strict qualification recomputes it
and rejects missing or mismatched provenance.
Set `require_independent_debate_judge_service` in
`workspace/orchestration-policy.json` to require the decision-maker judge to use
a configured and actual provider endpoint/model distinct from every participant.
`check` reports a non-blocking warning for a shared configured judge. With the
strict policy enabled, `qualify` blocks before debate starts and revalidates the
selected participant roles after a checkpoint exists.
Debate results store `judge_provenance_sha256`, binding verdict, evidence digest,
participant identities, and judge identity for handoff and qualification checks.

`qualify` consolidates compilation, manifest, service configuration, evidence,
and decision-gate checks. A passing report without test execution is `ready`.
Manifest validation is fail-closed: the manifest must be a regular JSON-object
file with project metadata and a non-empty, duplicate-free list of regular files
inside the project root. Unsafe, missing, directory, and symlink entries fail the
report, and the standalone `manifest` command exits nonzero.
Only `qualify --run-verification` can produce `qualified`; add
`--probe-services` to include live endpoint probes. Standard OpenAI-compatible
and Ollama model-list responses are also checked for the configured model;
unrecognized compatible response formats fall back to connectivity status.
Reports and next actions are
stored under `workspace/qualifications/`.

`runs` combines durable pipeline, debate, and repair checkpoints into one
content-redacted JSON view. Use `--unresolved` to show only sessions that need
attention. Each entry includes bounded progress, failure reason, and a safe
resume, abandon, or inspection action without exposing prompts or AI outputs.

`verification-run` executes only commands that appear both in the accepted
decision record and `workspace/verification-policy.json`. Argument-level policy
matching preserves quoted content and rejects shell operators and control
characters. Bare Python launchers resolve to the current runtime while explicit
interpreter paths remain unchanged. Commands run without a shell, with time and
output limits, and their results are saved under `workspace/verifications/`.

Patch commands accept UTF-8 unified diffs. `workspace/repair-policy.json`
controls editable roots and size limits. The runtime validates every hunk before
writing, stores original files under `workspace/patches/`, and refuses rollback
when a file changed after the patch.
Diff headers accept slash or Windows-style separators and LF or CRLF input while
preserving each existing target file's newline convention.

Workspace snapshots exclude symlinks and generated snapshot trees. Restoring a
snapshot replaces captured directories, preserves the snapshot history itself,
rejects paths outside the snapshot directory, and removes temporary restore data.

`archive` performs a complete size and file-count preflight before creating a
ZIP. `workspace/archive-policy.json` excludes archives, VCS metadata, bytecode,
symlinks, and common secret-key files by default. A policy failure leaves no
partial ZIP. Every ZIP contains a SHA-256 inventory; `archive-verify` validates
that inventory, member sizes, duplicate names, and path traversal safety without
extracting the archive. Pass `--file PATH` to inspect a specific ZIP.

`audit-check` validates every JSONL record, required event fields, timezone-aware
timestamps, and the SHA-256 record chain instead of silently discarding damaged rows.
The first version-2 event anchors any legacy prefix; later events detect valid-JSON
changes, insertion, deletion, and reordering. This is consistency detection, not a
cryptographic signature against an attacker who can rewrite the file and hashes.
`audit-export` writes the
complete records, event counts, and validation findings under `workspace/reports/`.
Qualification includes the content-redacted audit summary and blocks readiness
when any row, required field, or timestamp is invalid. Event records themselves
are not copied into the qualification report.
Scorecard JSON and boolean check values are also validated fail-closed. A damaged
scorecard is preserved, summarized without its contents, and blocks qualification.

`repair-run` executes verification, debugger diagnosis, policy-limited file
context collection, coder diff generation, safe patch application,
reverification, and an independent reviewer verdict. Failed or rejected patches
are rolled back by default. Session records live under `workspace/repairs/`.
`repair-resume` validates the saved patch hashes and continues the same attempt
from its last durable debugger, diff, patch, verification, or reviewer stage.
Completed AI stages are not repeated, and their elapsed-time and AI-call usage
still counts toward the restored budget. Failed or rejected work is rolled back
before a linked session receives only the remaining attempt count. A file changed
after patch application blocks resumption instead of overwriting user work.

`invoke --json` returns a redacted invocation report with every primary and
fallback attempt, duration, provider identity, HTTP status, retryability, and
error category. Pipeline execution JSON and AI cache entries preserve the same
diagnostics. Final invocation failures print the structured report to stderr;
prompts, response bodies, credentials, URL user information, and query strings
are not included in diagnostics or audit events.

`role-plan` classifies English or Korean task text using deterministic local
rules and recommends roles in the enforced forward order. The saved plan reports
service assignment, disabled services, decision-gated coder/reviewer roles, and
safe next-command templates without invoking a model or executing the task.
Plans are stored under `workspace/orchestration/`.
`orchestrate` executes that deterministic plan through the existing durable
engines. `planning` runs the forward planning pipeline, `debate` runs planning
roles followed by the separate decision-maker judge, and `repair` runs the
bounded debugger/coder/reviewer loop. Required service assignments and the
decision gate are checked before any provider call. Each stage keeps the same
budgets, checkpoints, cache, resume, rollback, and qualification behavior as its
underlying command.
Every invocation also writes a content-redacted wrapper checkpoint under
`workspace/orchestration/executions/`. `orchestrate-status` shows its plan ID,
task hash, stage, options, status, and linked pipeline/debate/repair session
without duplicating task text or AI outputs. Failed wrapper executions remain
inspectable even when the command exits nonzero.
New plans and wrapper checkpoints use format v2 and hash their complete stored
provenance. The wrapper binds both the plan hash and redacted task hash to the
original saved plan and validates stage, child identity, and terminal status consistency. Historical
`runs` and qualification scans use the same canonical loader, so a modified
completed wrapper is reported as an invalid checkpoint instead of being hidden.
Plan loading re-derives task tags, recommended roles, and planning roles from
the task. It also validates role/service snapshots, blocker summaries,
invocability flags, decision-gate structure, and bounded command templates.
Blockers are recomputed from each service snapshot and gate state, while the
exact command sequence is regenerated from task tags and planning roles.
Role order must exactly match the saved plan for the selected stage, and bounded
round, retry, and repair-attempt options are validated before plan creation and
again whenever a format-v2 wrapper is loaded.
The wrapper reserves and persists the child session ID before calling the stage
engine. A hard interruption therefore leaves a usable pipeline, debate, or
repair ID in `orchestrate-status` instead of an unlinked running wrapper.
The reservation is deterministically derived from the wrapper ID and task hash.
Canonical loading rejects any other linked child ID even if the wrapper hash was
recomputed, and a stage engine returning a different ID is recorded as failure.
Child status is restricted to the durable states produced by its stage engine.
The loader also rejects impossible lifecycle pairs such as a running wrapper
linked to a completed child or an abandoned wrapper linked to active work.
Lifecycle timestamps must be timezone-aware and monotonic. Running and completed
wrappers cannot retain errors, failed wrappers require a bounded error, and
abandoned wrappers require a reason plus an in-range abandonment timestamp.
`orchestrate-resume` verifies the saved plan identity and task hash. If the
reserved child checkpoint exists it delegates to that engine's resume command;
if interruption happened before child creation it starts the stage with the
same reserved ID. Completed wrappers resume idempotently without provider calls.
`orchestrate-reconcile` repairs wrapper status from an existing child checkpoint
without invoking a provider or continuing work. It is useful after interruption
between child completion and wrapper completion.
`orchestrate-reconcile-all` applies that recovery to terminal children in
multiple wrappers and skips active or missing children.
An orchestration wrapper completes only when its child reaches a stage-specific
success state. Exhausted repair attempts, budget exhaustion, stale debates, and
other terminal non-success results keep the wrapper failed and visible.
`orchestrate`, `orchestrate-resume`, and `orchestrate-reconcile` return process
exit code `0` only for a completed wrapper and `2` for a recorded non-success
result. `repair-run` and `repair-resume` similarly return `0` only for
`approved` or `already_verified`, and `2` for durable unsuccessful terminal
states. Reconcile-all returns `1` when any wrapper could not be inspected.
Repair revalidates the decision gate before reviewer invocation and again before
persisting approval. A decision or evidence change during review prevents stale
approval; an applied patch follows the configured rollback path.
This also applies to an approval verdict saved immediately before interruption:
resume rechecks the gate and rolls back its patch instead of finalizing stale approval.
Failed, interrupted, or corrupt orchestration wrappers appear in
`runs --unresolved` and block qualification history. The report recommends
reconcile, resume, or abandon from the linked child's durable state. Resolve a superseded
wrapper with `orchestrate-abandon` and a reason. When a linked pipeline,
debate, or repair checkpoint exists, the command abandons that child first.
The wrapper remains unresolved if child cleanup or repair rollback fails.
Historical validation also follows terminal wrapper links. Completed wrappers
require an existing canonical child checkpoint, while abandoned wrappers may
omit one only when the child was explicitly recorded as `not_started`; stored
and actual terminal child statuses must match.
The wrapper task hash must also equal the canonical child's stored prompt/task
hash for pipeline, debate, and repair links. A valid child from another task
therefore cannot satisfy a terminal wrapper merely by occupying its path.
Pipeline and debate child role order must equal the wrapper role contract.
Planning pipelines also require the fixed evidence-aware system prompt, and
pipeline/debate retry options must equal the wrapper's saved option.
Debate rounds are policy-clamped before the wrapper and child are created, so
both checkpoints store the same effective count. Terminal debate rounds must
match exactly; repair attempts must be valid and cannot exceed the wrapper request.

Every `pipeline` execution has a distinct run ID and durable session under
`workspace/executions/runs/`. `pipeline-status` exposes the latest or selected
checkpoint. After a role failure, `pipeline-resume` continues with the first
unfinished role and reconstructs its context from saved outputs; completed roles
are not invoked again. Resuming a completed run is idempotent.
New pipeline checkpoints use format v2. Each role result hashes its full stored
provenance, including content, service identity, diagnostics, and context metadata.
The canonical loader also validates session identity, input hash, status, role
sequence, and completed result count. `runs` and qualification apply this loader
to historical checkpoints, so a tampered completed run cannot hide as resolved.
Format-v1 checkpoints remain readable with their existing content-hash checks.
`workspace/orchestration-policy.json` bounds role count, prompt and system size,
carried context, elapsed execution time, and cumulative AI calls. The selected
limits and consumed budget are checkpointed with the run, and budget exhaustion
is terminal. Older role outputs are omitted or truncated before model context
can exceed the configured bound.
The same policy defines minimum and maximum role-output sizes. Responses outside
that contract consume the reserved call, fail before handoff, and can be retried
from the same role with `pipeline-resume`.
Runtime checkpoints are flushed to same-directory temporary files and atomically
replaced under per-file locks. Audit append and scorecard updates are also
locked. Pipeline, debate, and repair resume or abandon operations use PID-owned
session locks, preventing concurrent commands from repeating pending AI work
and recovering locks left by dead processes.
Existing mutable JSON is fail-closed: malformed content or a non-object root
raises a content-redacted error before the mutator runs. State and scorecard
files are never reset to an empty object merely because parsing failed.
If a process stops after saving a durable session but before updating its
`latest` copy, status, resume, and qualification select the newest original
checkpoint by its saved update timestamp instead of hiding the interrupted run.
Pipeline role calls reserve an in-flight slot before provider invocation and
cache a contract-valid success before writing the role checkpoint. If the
process stops in that gap, resume keeps the original AI-call charge and restores
the cached response without calling the provider again. Invalid role output is
not cached. Concurrent requests with the same cache key use a single-flight
lock: one request calls the provider while the others wait and reuse its saved
success. Each pipeline still retains its own logical AI-call budget reservation.
Cache format v2 uses canonical service routes, so harmless provider aliases and
equivalent URLs share entries. Enabled-state changes, configuration failures,
and API-key rotation produce new keys. Credential fingerprints affect only the
final key calculation and are never stored in cache entries or audit records.
Each cache entry also binds its file key, role, content, service metadata, and
diagnostics with `result_sha256`. A changed or renamed entry is never replayed
and is reported as invalid for lock-safe pruning.
`ai-cache-status` reports only entry counts, age state, and total bytes.
`ai-cache-prune` removes expired and malformed entries under the same per-key
locks; add `--all` to deliberately clear fresh entries as well.
`qualify` validates the orchestration policy and the latest pipeline checkpoint.
Failed, running, pending, budget-exhausted, or corrupt latest runs block readiness.
Use `pipeline-abandon` with a recorded reason when a failed run is intentionally
superseded; abandoned and completed runs are resolved states.
Qualification also scans every durable pipeline, debate, and repair session, so
a newer successful run cannot hide older unresolved or corrupt work. Resolve the
full list shown by `runs --unresolved` before claiming readiness.

The repair policy also limits total elapsed time, AI call count, and generated
tokens per call. Budget exhaustion is checkpointed as a terminal state and any
active patch is rolled back before the loop stops.
Unresolved latest repair sessions block qualification readiness. Use
`repair-abandon` with a recorded reason to resolve superseded work. Any active
patch is rolled back first; a user-change conflict keeps the session
`rollback_blocked` instead of falsely resolving it. Approved and already-verified
sessions cannot be abandoned, and abandoned sessions cannot be resumed.
When repair resume hands remaining attempts to a new session, the original is
closed as `superseded` with the successor ID while the latest pointer remains on
the successor.
New repair sessions use format v2 and refresh a canonical whole-session SHA-256
at every durable save. The hash covers task metadata, budgets, attempts,
verification, patch and rollback records, service identities, and reviewer data.
Canonical loading validates identity, status, attempt ordering, approved review
provenance, and the session hash. Historical `runs` and qualification scans use
the same loader; existing format-v1 sessions remain readable.

Repair AI responses are cached by role, model service, prompt, and generation
settings under `workspace/cache/ai/`. Exact retries reuse successful responses;
changed prompts or model routing create new keys. Multi-round debate results and
the structured decision-maker verdict are stored under `workspace/debates/`.
The verdict must include a decision, rationale, agreements, disagreements,
risks, confidence, implementation brief, and proposed verification commands.
Its canonical SHA-256 is checked before `decision-draft` uses it. A valid latest
verdict replaces the generic decision text; a tampered verdict blocks drafting.
Proposed commands remain subject to `workspace/verification-policy.json`.
The report also records the current evidence/claim/policy input digest and the
verdict's accepted `claim_ids`. Evidence changes make the debate stale, and all
accepted claims required by policy must be referenced before drafting can
continue. Rerun `debate-rounds` after changing verified knowledge.
Multi-round debates are durable sessions. `debate-status` exposes the current
round, linked pipeline, completed rounds, and judge stage. `debate-resume`
continues a failed linked pipeline or retries only the judge after all rounds
finish. Completed rounds and completed debate sessions are idempotent. Evidence
changes before judgment make the session terminal `stale`. Qualification treats
failed, stale, running, budget-exhausted, or corrupt latest debate sessions as
readiness blockers. The orchestration policy also fixes debate-wide round,
elapsed-time, and AI-call limits. Role slots are reserved before each round and
judge attempt, and their cumulative usage survives process failure and resume.
Use `debate-abandon` with a recorded reason to resolve a superseded unfinished
session without presenting it as completed. Completed sessions cannot be
abandoned, and abandoned sessions cannot be resumed.
New debate sessions use format v3: every round hashes its complete role-output
provenance. Format-v2 final reports hash the verdict, rounds, actual service
independence, participant identities, and judge identity as one result. Canonical
validation runs during resume, status history scans, and qualification, so a
tampered historical completion becomes an `invalid_checkpoint`. Existing
format-v2 sessions retain compatible validation.
Hash-valid version 1 debate checkpoints created before debate-wide budgets are
upgraded in memory on load. Their completed work and in-flight stage are counted
conservatively before resume; an invalid legacy hash is never migrated.
Evidence and claim mutations are serialized so concurrent CLI commands cannot
lose records. Lock and atomic-write temporary files are excluded from archives.

`evidence-check` applies `workspace/evidence-policy.json`. New projects require
two distinct evidence URLs by default, validate confidence and retrieval time,
reject normalized duplicates, and can optionally enforce search-plan coverage.
Structured JSON is authoritative and is saved before the generated Markdown view.
`evidence-check` returns nonzero when an existing Markdown view is stale;
`evidence-rebuild` safely regenerates it from JSON after an interrupted write.
CI-facing checks use a consistent exit contract: `gate`, `verify`, `claim-check`,
`evidence-check`, `verification-plan`, `verification-run`, `archive-verify`,
`audit-check`, `manifest`, and `check` return `0` only when their reported
condition passes, and `1` when it fails.
New projects also require a structured claim matrix. `claim-add` links each
accepted, uncertain, or rejected claim to known supporting and challenging
evidence URLs. Accepted claims require support; challenges require a substantive
resolution; and accepted claim IDs or text must appear in the decision record.
`claim-check` validates the matrix. Existing projects receive this feature with
`require_claim_matrix: false` during migration so their current gate does not
close unexpectedly; enable it after adding claims.
Evidence records must be a JSON list of objects and the search plan must be a
JSON object. Malformed or wrong-root files close the decision gate and fail
qualification with content-redacted path/location issues. Evidence mutations
stop before writing, preserving the damaged original for recovery.
New projects also bind each generated decision draft to a SHA-256 snapshot of
the current evidence, claims, and evidence policy. Any later change closes the
implementation gate until the decision is reviewed and regenerated. Migrated
projects receive `require_decision_snapshot: false` for compatibility.
`evidence-fetch` retrieves one explicit source URL, extracts bounded text, and
commits it as structured evidence. The same policy controls time, response size,
content types, optional domain allowlists, and private-network access. Redirects
are revalidated and private or loopback destinations are blocked by default.
Fetched records include a SHA-256 fingerprint of normalized visible source text.
`evidence-source-check` safely refetches one recorded URL and returns nonzero when
the content or final redirect URL changed, storing only hashes and metadata under
`workspace/evidence/source-verifications/`. New projects require fingerprints
for `direct_url` records; migrated projects keep this requirement disabled until
their direct evidence is recaptured.
Once a check detects change, evidence policy and qualification remain blocked.
After reviewing the new source, `evidence-source-refresh` atomically replaces
that record and stores a matching verification. The changed evidence snapshot
then keeps the implementation gate closed until the decision is regenerated.
Set `require_source_revalidation` and `max_source_verification_age_days` to make
recent successful checks mandatory instead of on-demand.
`evidence-source-check-all` checks every fingerprinted HTTP source up to
`max_source_checks_per_run`, continues after individual failures, and exits
nonzero for changes, errors, or skipped candidates. Its content-redacted batch
report is stored under `workspace/evidence/source-verifications/`.
Evidence drafts supplied to `evidence-commit` must resolve inside the project.

`search-discover` optionally queries a configured self-hosted SearXNG JSON API.
It is disabled by default in `workspace/search-policy.json`. Query count, result
count, timeout, response size, endpoint domains, and private-network access are
policy bounded. Discovered URLs are saved under
`workspace/evidence/discoveries/` as unapproved candidates and never satisfy the
evidence gate until their direct sources are fetched and validated.

After changing runtime templates, synchronize existing generated projects:

```powershell
python scripts\sync_generated_projects.py
```

Check local services:

```powershell
.\scripts\check-services.ps1
```

Start the 14B coder profile:

```powershell
.\scripts\start-vllm-coder-14b.ps1
```

Start the Nemotron planner profile:

```powershell
.\scripts\start-vllm-planner-nemotron.ps1
```

Restore the Qwen3-8B fallback profile:

```powershell
.\scripts\start-vllm-fallback-qwen3-8b.ps1
```

## Required Services

vLLM planner/coder/fallback endpoint:

```text
http://127.0.0.1:8000/v1
```

Optional Ollama backup planner endpoint:

```text
http://127.0.0.1:11434
```

## Recommended Runtime

Planner context:

```text
8192 or 12288 tokens to start
```

Coder context:

```text
8192 or 12288 tokens to start
```

Keep patches small. Do not ask one model to plan, edit, test, and judge in a
single pass.

## Design Discussion Workflow

Start the local UTF-8 web form:

```powershell
python .\src\haness_frame.py serve
```

Then open:

```text
http://127.0.0.1:8765/
```

Use this web form when the original request contains Korean or other non-ASCII
text. The generated harness files still use the English working description.

Configure AI services in the same local web server:

```text
http://127.0.0.1:8765/settings
```

The AI services page supports:

```text
- service company
- provider type
- model
- base URL
- API key environment variable name
- enabled/disabled state
- multiple roles per service
- edit/update/delete
```

Supported role examples:

```text
project_scout, context_curator, researcher, planner, designer, architect,
critic, debugger, decision_maker, coder, reviewer, escalation
```

Configure UI language:

```text
http://127.0.0.1:8765/preferences
```

Language packs live under:

```text
lang/
```

The user-selected language is stored in a browser cookie. The server default
language is stored in SQLite.

Manage generated projects:

```text
http://127.0.0.1:8765/projects
```

Each project detail page includes a ZIP download link. Download URLs use this
form:

```text
http://127.0.0.1:8765/download?name=<project-slug>
```

Project detail pages also let you assign AI services to roles for that project:

```text
http://127.0.0.1:8765/project?name=<project-slug>
```

Saved role routing lives in:

```text
projects/<project-slug>/project-settings.json
projects/<project-slug>/docs/04-agent-routing.md
projects/<project-slug>/docs/05-project-settings.md
```

Settings are stored in SQLite:

```text
data/haness.db
```

Default service rows include local vLLM, Ollama, Codex, and Claude placeholders.
API keys should be stored in environment variables and referenced by name in the
`api_key_env` field.

Create a full project harness workspace:

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" "Build an internal business system for approvals, tasks, documents, and reporting"
```

Recommended rule: keep generated harness files in English. If the original
request is not English, pass an English working description:

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" --english-description "Build an internal business system for approvals, task requests, document management, messaging, leave requests, and organization management" "Build an internal business system"
```

The original request is stored only in:

```text
context/original-request.md
```

This creates:

```text
projects/internal-business-system/
  README.md
  AGENTS.md
  CLAUDE.md
  context/original-request.md
  docs/00-workflow.md
  docs/00-runtime-map.md
  context/business-context.md
  context/source-materials.md
  research/search-backlog.md
  docs/01-project-discovery.md
  docs/02-role-discussion.md
  docs/03-decision-record.md
  docs/04-agent-routing.md
  docs/05-project-settings.md
  docs/06-system-runtime.md
  docs/07-roadmap.md
  prompts/role-briefs.md
  implementation/README.md
  workspace/state.json
  workspace/services.json
  workspace/manifest.json
  workspace/scorecard.json
  src/harness_app/
```

Create a design session file:

```powershell
python .\src\haness_frame.py design-template --write --project "pycapture-tool-pro" "Add role-based internet research and debate"
```

Create a shorter discussion skeleton:

```powershell
python .\src\haness_frame.py discuss --write --project "pycapture-tool-pro" "Design a local coding harness workflow"
```

Generated harness documents are written under:

```text
projects/<project-slug>/docs/
```

If `--project` is omitted, the project folder name is derived from the task.

The intended loop is:

```text
Project Scout -> Researcher -> Planner -> Designer -> Architect -> Critic -> Planner -> Decision Maker -> Coder
```

All roles may use internet search. Use Google when alternatives, current docs,
exact errors, known limitations, or ecosystem comparisons are needed. The
researcher coordinates evidence, but search is available to planner, designer,
architect, critic, debugger, coder, and decision maker. The coder should receive
only the accepted implementation brief.

For a new project request, the harness starts with Google project discovery.
It should look for related projects, existing products, open source repositories,
alternatives, architecture examples, and common failure modes before planning.
