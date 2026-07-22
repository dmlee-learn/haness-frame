# $project_name

Created: $created_at

## Overview

This workspace is a runnable harness engineering system, not only a template.
It includes the project documents, role routing metadata, and a small stdlib
CLI that can bootstrap workspace state, render role packets, and report the
current workflow stage.

## Working Description

$working_description

## Runnable System

```text
python app.py init
python app.py status
python app.py roles
python app.py pack --role planner
python app.py render
python app.py invoke --role planner --prompt "Summarize the project state"
python app.py pipeline --prompt "Draft a first-pass design plan"
./run.ps1 implement --task "Implement the approved change"
./run.ps1 finish
```

After the decision gate and verification policy are ready,
`./run.ps1 implement --task "..."` asks the coder for a patch, repairs malformed
diff hunk counts, validates and applies it, runs the approved tests, rolls back
on failure, and finishes the qualified archive on success.

After implementation, `./run.ps1 finish` validates the approved commands,
runs qualification, creates an archive, and verifies its integrity.

## Workflow

1. Bootstrap the runtime workspace.
2. Fill `context/business-context.md`.
3. Run the Google searches listed in `research/search-backlog.md`.
4. Summarize findings in `docs/01-project-discovery.md`.
5. Complete the role discussion in `docs/02-role-discussion.md`.
6. Finalize the build decision in `docs/03-decision-record.md`.
7. Render role packets from the state stored in `workspace/state.json`.
8. Start implementation from `implementation/README.md` after the decision is accepted.

## Project Folders

```text
context/          Internal business and domain context
research/         Search backlog and external evidence
docs/             Workflow, discovery, discussion, and decision records
prompts/          Role-specific prompt briefs
implementation/  Build notes after a decision is accepted
workspace/        Runtime state, role packets, and execution artifacts
src/              Runnable harness engine package
```
