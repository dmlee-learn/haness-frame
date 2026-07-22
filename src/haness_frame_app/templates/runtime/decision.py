from __future__ import annotations

import datetime as dt

from .evidence import evidence_summary
from .claims import claim_summary
from .debate import load_latest_debate_verdict
from .provenance import decision_input_digest
from .storage import read_text, write_text


def _safe_line(value: object, max_chars: int = 1000) -> str:
    return " ".join(str(value).replace("`", "'").split())[:max_chars]


def _bullet_list(value: object) -> str:
    if not isinstance(value, list):
        raise ValueError("debate decision collection must be a list")
    return "\n".join(f"- {_safe_line(item)}" for item in value)


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
    claims = claim_summary()
    input_digest = decision_input_digest()
    verdict = load_latest_debate_verdict()
    if verdict:
        accepted_decision = f"- {_safe_line(verdict['decision'])}"
        rationale = f"- {_safe_line(verdict['rationale'])}"
        agreements = _bullet_list(verdict["agreements"])
        disagreements = _bullet_list(verdict["disagreements"])
        risks = _bullet_list(verdict["risks"])
        implementation_brief = _bullet_list(verdict["implementation_brief"])
        verification_commands = "\n".join(f"- `{_safe_line(item)}`" for item in verdict["verification_commands"])
        confidence = _safe_line(verdict["confidence"])
        debate_claims = _bullet_list(verdict["claim_ids"]) or "- none"
    else:
        accepted_decision = "- Proceed with the harness runtime split, structured search evidence, and decision-gated role orchestration."
        rationale = "- The harness requires deterministic, evidence-gated implementation."
        agreements = "- Preserve evidence and independent verification."
        disagreements = "- No structured debate verdict is available."
        risks = "- The decision draft requires human review before implementation."
        implementation_brief = "\n".join(
            [
                "- Keep role orchestration deterministic.",
                "- Preserve evidence capture and decision gate enforcement.",
                "- Keep runtime modules small and aligned with the generator.",
            ]
        )
        verification_commands = "\n".join(
            [
                "- `python -m compileall src`",
                "- `python app.py manifest`",
                "- `python app.py search-plan`",
                "- `python app.py verify`",
                "- `python app.py scorecard`",
            ]
        )
        confidence = "not-rated"
        debate_claims = "- No structured debate claim references are available."
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

{accepted_decision}

## Decision Rationale

{rationale}

## Debate Agreements

{agreements}

## Debate Disagreements

{disagreements}

## Debate Risks

{risks}

## Debate Confidence

- {confidence}

## Debate Claim References

{debate_claims}

## Context

- The harness is organized around role-based execution.
- Coder and reviewer actions are blocked until evidence and decision notes are present.
- Runtime modules are split across small files under `templates/runtime/`.

## Evidence Used

{evidence}

## Claims Accepted

{claims}

## Evidence Snapshot

- input_digest: `{input_digest}`

## Rejected Options

- Allowing coding before the decision record is complete.
- Keeping all runtime behavior in one large source file.

## Implementation Brief For Coder

{implementation_brief}

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
