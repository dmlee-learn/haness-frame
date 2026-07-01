# Agent Routing

Working description:

```text
$working_description
```

## Role To Service Mapping

$rows

## Rules

1. Use the service assigned to the role when available.
2. If the assigned service is disabled, fall back to another service that
   advertises the same role.
3. If no match exists, use the local fallback service.
4. Do not ask the coder to discover the design. Keep research and discussion
   before implementation.

