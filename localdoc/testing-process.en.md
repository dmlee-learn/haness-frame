# Testing Process

## Test Layers

1. Compile the main source with `python -m compileall src`.
2. Synchronize generated projects with `python scripts\sync_generated_projects.py`.
3. Run `python app.py verify` in a gate-blocked smoke project.
4. Run `python app.py verify` in a gate-approved smoke project.
5. Confirm `summary` reports evidence plans, coverage, gaps, and the decision gate accurately.
6. Confirm `verification-plan` rejects commands absent from the project policy.
7. Confirm `verification-run` records approved command output and stops on failure.
8. Confirm patch traversal and context mismatches are rejected before writing.
9. Confirm patch rollback refuses to overwrite later user changes.
10. Confirm repair approval requires passing verification and an independent reviewer verdict.
11. Confirm direct URL evidence retrieval blocks private networks, disallowed domains, and oversized responses.
12. Confirm deterministic mock OpenAI-compatible and Ollama services satisfy request, response, and fallback contracts.
13. Run the complete repair CLI in a child process and confirm failed test, diagnosis, patch, retest, and reviewer approval artifacts.
14. Confirm snapshot restore preserves snapshot history, removes temporary data, and rejects path traversal.
15. Confirm evidence drafts stay inside the project and invalid role sequences fail before AI execution.
16. Confirm concurrent processes share identical AI calls and cache maintenance never exposes response content.
17. Confirm direct evidence fingerprints detect normalized source stability and material content changes without storing bodies.
18. Run the Golden E2E in one generated project through evidence, claim, debate, decision, gate, repair, test, review, and qualification.

## Expected Results

- A new project is blocked before evidence and an accepted decision exist.
- Invalid evidence and incomplete decision sections keep the gate closed.
- A completed evidence record and decision brief allow coder and reviewer execution.
- Runtime modules compile and every manifest entry exists.
- Shell operators are rejected even if their complete text appears in the policy.
- Verification cannot run while the decision gate is closed.
- Valid patches create backups and auditable metadata before repair orchestration continues.
- Failed verification rolls back the patch and consumes only the configured attempt budget.
- Direct URL evidence is committed only after URL, redirect, content type, and response limits pass.
- Retryable primary provider failures switch to a distinct configured fallback service.
- Same-size Python source patches invalidate stale bytecode before reverification.
- Snapshot restoration does not delete its own recovery history.
- Empty, duplicate, unknown, and backward role sequences are rejected.

## Optional Environment-Dependent Test

When a real local provider is running, execute service probes and a live role
invocation with `python app.py live-check --role planner`. The command returns a
content-redacted JSON result and a nonzero exit code on failure. Model
installation and availability are environment-dependent, so
this is not mandatory in the default automated suite. Model-specific tuning and
vLLM configuration are outside this release scope.
