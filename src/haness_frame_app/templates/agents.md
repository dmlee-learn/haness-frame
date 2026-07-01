# AGENTS.md

Project:

```text
$project_name
```

Working description:

```text
$working_description
```

## Rules

1. Keep changes small and reversible.
2. Prefer existing project files and current conventions.
3. Do not write implementation code before the decision record is approved.
4. Use `workspace/state.json` as the runtime source of truth.
5. Render role packets before starting review or coding work.

## Workflow

`context` -> `research` -> `discussion` -> `decision` -> `implementation`

## Required Checks

- `python app.py status`
- `python app.py next`
- `python app.py render`
- `python -m compileall src`

## Notes

The generated workspace is a runnable harness system. Keep file names in
English and keep the original request only in `context/original-request.md`.

