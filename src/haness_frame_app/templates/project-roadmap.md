# Project Roadmap

Working description:

```text
$working_description
```

## Priority 1

1. Resolve the service snapshot in `workspace/services.json`.
2. Use the snapshot to call the assigned AI provider.
3. Save the request and response for each role.
4. Add a fallback path when a role service fails.
5. Expose a project-local `invoke` command.

## Priority 2

1. Run the role pipeline in order.
2. Produce search evidence and discussion notes.
3. Enforce the decision gate before coding.
4. Update `workspace/scorecard.json`.

## Priority 3

1. Add retry and timeout handling.
2. Add manifest validation.
3. Add execution logs.
4. Add rollback support.

## Later

1. Search integration
2. Tool-call support
3. Multilingual expansion
4. Batch project operations
