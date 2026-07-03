# haness-frame testing process

## Purpose
Keep the harness runtime, the generated projects, and the decision gate aligned while development continues.

## Test order
1. Run `python -m compileall src` in the generator workspace.
2. Run `python app.py summary` in a generated project to check counts and next action.
3. Run `python app.py search-plan` to refresh the plan, evidence draft, and gap report.
4. Review `research/search-evidence-draft.md` and `research/search-evidence-gaps.md`.
5. Capture evidence with `python app.py add-evidence ...` or `python app.py evidence-commit`.
6. Regenerate the decision record with `python app.py decision-draft`.
7. Run `python app.py verify` to check compileall, manifest validation, and the decision gate.
8. If the runtime templates changed, run `python scripts/sync_generated_projects.py`.

## What each command checks
- `compileall`: syntax and import-level breakage in the generator.
- `summary`: whether the project has documents, evidence, gaps, and an open or closed gate.
- `search-plan`: whether the backlog is still producing the expected search targets.
- `evidence-draft` and `evidence-gaps`: whether research work still needs to be done.
- `evidence-commit`: whether a draft can be turned into structured evidence without schema drift.
- `decision-draft`: whether the accepted decision and implementation brief can be regenerated from current context.
- `verify`: whether the current project is ready to move forward.

## Practical rule
- Run `summary` and `verify` on the generated project before and after any template change.
- Run `compileall` on the generator workspace after every code edit.
- Run `sync_generated_projects.py` after changes to runtime templates.
