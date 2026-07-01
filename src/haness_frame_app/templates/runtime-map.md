# 00 Runtime Map

Project:

```text
$project_name
```

Working description:

```text
$working_description
```

## Runtime Order

1. Load `workspace/state.json`.
2. Load `workspace/services.json` for resolved role endpoints.
3. Check `workspace/scorecard.json`.
4. Render role packets.
5. Review `docs/03-decision-record.md`.
6. Start implementation only after approval.

## Files That Drive Execution

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/skills/haness-frame/SKILL.md`
- `workspace/state.json`
- `workspace/services.json`
- `workspace/scorecard.json`
- `docs/03-decision-record.md`
