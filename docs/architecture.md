# Harness Architecture

## Product Purpose

The harness helps people using local AI create reliable, working programs with
a strong but approachable engineering workflow. It coordinates specialized AI
roles, evidence-backed decisions, implementation, executable verification, and
bounded repair attempts. Local services remain the default and cloud escalation
is optional.

## Design Invariants

```text
- No coding role runs before the evidence and decision gate passes.
- A role may not approve its own implementation without independent review.
- Every accepted implementation brief includes executable verification commands.
- Every repair attempt is bounded, logged, and based on the latest failure.
- User changes outside the accepted implementation scope are preserved.
- Interrupted work can be inspected and resumed from recorded state.
- Role pipelines isolate each run and never repeat a completed role during resume.
```

## Automated Repair Contract

```text
1. Run policy-approved verification commands.
2. Ask debugger for JSON diagnosis and relevant project-relative files.
3. Load only files allowed by repair-policy context limits.
4. Ask coder for exactly one unified diff.
5. Validate and apply the patch with backups.
6. Re-run verification.
7. Ask an independent reviewer for a JSON verdict.
8. Keep an approved patch or rollback and retry within the attempt budget.
```

Invalid AI response formats, unsafe paths, patch context mismatches, failed
tests, and reviewer rejection cannot produce an approved session.

## Roles

### Planner / Reviewer

Default local candidate:

```text
nvidia/NVIDIA-Nemotron-Nano-9B-v2 through vLLM
```

Responsibilities:

```text
- Break down the task.
- Select relevant files.
- Summarize long logs.
- Identify likely root causes.
- Produce a patch checklist.
- Prepare a compact escalation brief for Gemini.
```

Restrictions:

```text
- Must not generate the final diff.
- Must not decide dependency upgrades alone.
- Must not rewrite large files.
```

### Coder

Default local candidate:

```text
Qwen/Qwen2.5-Coder-14B-Instruct-AWQ through vLLM
```

Responsibilities:

```text
- Generate focused patches.
- Fix test failures.
- Adjust imports, types, and integration details.
- Keep changes narrow.
```

### Fallback

Default:

```text
Qwen/Qwen3-8B-AWQ through vLLM
```

Use for:

```text
- Light edits.
- Tool-call compatible workflows.
- Fast checks when 14B is too slow.
```

### Escalation

Use Gemini only when local models fail repeatedly or the issue requires broad
architecture judgment.

## Loop

```text
1. Planner receives the user task and repository summary.
2. Planner returns file candidates and an execution plan.
3. Harness reads only relevant files.
4. Coder receives the scoped context and patch contract.
5. Harness applies patch and runs tests.
6. If tests fail, coder gets the short failure log and tries again.
7. After repeated failure, planner analyzes the failure pattern.
8. If still blocked, harness sends a compact brief to Gemini.
```

## Context Rules

```text
- Do not send the whole repository by default.
- Prefer file outlines before full files.
- Include exact test command and failing output.
- Trim logs to the first causal error and final summary.
- Preserve user changes; never revert unrelated edits.
```

## Current Local Model Strategy

```text
Planner:
  NVIDIA-Nemotron-Nano-9B-v2 via vLLM

Coder:
  Qwen2.5-Coder-14B-Instruct-AWQ via vLLM

Fallback:
  Qwen3-8B-AWQ via vLLM
```

Backup planner:

```text
qwen3.5:35b Q2_K via Ollama
```

If the 14B coder is not running, use Qwen3-8B-AWQ as a temporary coder but
expect weaker code-specific performance.
