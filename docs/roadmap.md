# Harness Engineering Roadmap

## Scope

This roadmap tracks the harness engineering system itself, not a single
generated project.

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
- Sequential `pipeline` command with per-role saved outputs
- Fallback execution for dead role services

## Phase 3 Priority

1. Retry and timeout policy
2. Fallback model selection
3. Snapshot and rollback support
4. Manifest validation
5. More stable project settings UI

## Phase 4 Priority

1. External search integration
2. Debate and review loop automation
3. Multi-language growth
4. Tool-call support
5. Project archival and backup automation

## Nice To Have

- Automatic role recommendation by task
- Project progress dashboard
- Better provider-specific diagnostics
- Batch project generation
- Exportable audit trail

## Operating Rule

Do not expand the orchestration layer until Phase 1 can actually call a model
using the project-local service snapshot.
