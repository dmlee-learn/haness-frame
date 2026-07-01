# Harness Architecture

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
