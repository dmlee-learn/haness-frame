# SKILL.md

Project:

```text
$project_name
```

Working description:

```text
$working_description
```

## Purpose

This project is a runnable harness engineering workspace. The skill is to keep
the harness predictable, lightweight, and easy to recover.

## Execution Order

1. Initialize runtime state.
2. Check missing documents.
3. Render role packets.
4. Review the decision record.
5. Implement only after approval.

## Files To Prefer

- `app.py`
- `src/harness_app/`
- `workspace/state.json`
- `docs/03-decision-record.md`

## Output Rules

- Keep generated text short.
- Do not duplicate large blocks across files.
- Avoid speculative behavior that cannot be verified locally.

