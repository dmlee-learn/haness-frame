# CLAUDE.md

Project:

```text
$project_name
```

Working description:

```text
$working_description
```

## Claude Guidance

- Read `AGENTS.md` first.
- Follow the current decision gate before changing code.
- Prefer edits inside `src/harness_app/` and `workspace/`.
- Avoid broad refactors unless the change requires them.
- Use concise responses and preserve generated English filenames.

## Safe Defaults

- If state is unclear, inspect `workspace/state.json`.
- If role routing is missing, regenerate it from the current project settings.
- If the decision record is empty, stop and fill it before implementation.

