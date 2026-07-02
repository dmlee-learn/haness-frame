from __future__ import annotations

import datetime as dt

from .evidence import evidence_summary
from .storage import read_text, write_text


def _extract_working_description(text: str) -> str:
    marker = "Working description:"
    start = text.find(marker)
    if start == -1:
        return text.strip()
    tail = text[start + len(marker) :]
    block_start = tail.find("```")
    if block_start == -1:
        return tail.strip()
    tail = tail[block_start + 3 :]
    if "\n" in tail:
        tail = tail.split("\n", 1)[1]
    block_end = tail.find("```")
    if block_end == -1:
        return tail.strip()
    return tail[:block_end].strip()


def build_decision_record_draft() -> str:
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    working_description = read_text("context/business-context.md", "").strip()
    if not working_description:
        working_description = read_text("context/original-request.md", "").strip()
    else:
        working_description = _extract_working_description(working_description)
    evidence = evidence_summary().strip() or "- none yet"
    verification_commands = "\n".join(
        [
            "- `python -m compileall src`",
            "- `python app.py manifest`",
            "- `python app.py search-plan`",
            "- `python app.py verify`",
            "- `python app.py scorecard`",
        ]
    )
    return f"""# 03 Decision Record

Created at:

```text
{created_at}
```

Working description:

```text
{working_description}
```

## Accepted Decision

- Proceed with the harness runtime split, structured search evidence, and decision-gated role orchestration.

## Context

- The harness is organized around role-based execution.
- Coder and reviewer actions are blocked until evidence and decision notes are present.
- Runtime modules are split across small files under `templates/runtime/`.

## Evidence Used

{evidence}

## Rejected Options

- Allowing coding before the decision record is complete.
- Keeping all runtime behavior in one large source file.

## Implementation Brief For Coder

- Keep role orchestration deterministic.
- Preserve evidence capture and decision gate enforcement.
- Keep runtime modules small and aligned with the generator.
- Avoid changes to vLLM settings in this thread.

## Verification Commands

{verification_commands}

## Rollback Plan

- Take a snapshot before implementation.
- Use `python app.py rollback --name <snapshot>` if a change needs to be undone.

## Open Questions

- Which remaining workflow steps should be auto-generated next?
- Should the decision record be auto-filled from evidence once search evidence exists?
"""


def write_decision_record_draft(force: bool = False) -> str:
    del force
    return str(write_text("docs/03-decision-record.md", build_decision_record_draft()))


def write_decision_record_file() -> str:
    return write_decision_record_draft()
