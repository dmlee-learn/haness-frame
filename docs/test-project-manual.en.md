# haness-frame Test Project Manual

This manual explains how to create and verify a project workspace with `haness-frame`.

## Current supported flow

1. Create a project-specific harness workspace.
2. Generate business context, backlog, discovery, discussion, decision, and implementation docs.
3. Seed search evidence work with `summary`, `search-plan`, `evidence-draft`, and `evidence-gaps`.
4. Capture structured evidence with `add-evidence` or `evidence-commit`.
5. Regenerate the decision record with `decision-draft`.
6. Validate the workspace with `verify`.

## What is not automated yet

1. Live Google search execution.
2. Automatic search summarization.
3. Automatic multi-model role calls for every step.
4. Full autonomous code generation loops.

## Create a test project

Run this from the repository root:

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" "Build an internal business system for approvals, tasks, documents, and reporting"
```

## Verify the runtime

After generating a project, run:

```powershell
cd .\projects\internal-business-system
python app.py summary
python app.py search-plan
python app.py evidence-draft
python app.py evidence-gaps
python app.py decision-draft
python app.py verify
```

## Practical rule

Keep the generated project moving through evidence capture and decision-gate checks before implementation starts.

