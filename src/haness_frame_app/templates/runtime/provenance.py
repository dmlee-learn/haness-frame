from __future__ import annotations

import hashlib
import json
import re

from .evidence_policy import load_evidence_policy
from .storage import read_text

EVIDENCE_FILE = "workspace/evidence/search-evidence.json"
CLAIMS_FILE = "workspace/evidence/claim-evidence.json"
DECISION_FILE = "docs/03-decision-record.md"
SNAPSHOT_HEADING = "Evidence Snapshot"
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.IGNORECASE)


def _json_value(path: str, default: object) -> object:
    try:
        return json.loads(read_text(path, json.dumps(default)))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def decision_input_digest() -> str:
    payload = {
        "evidence": _json_value(EVIDENCE_FILE, []),
        "claims": _json_value(CLAIMS_FILE, []),
        "evidence_policy": load_evidence_policy(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decision_snapshot_issues() -> list[str]:
    policy = load_evidence_policy()
    required = policy.get("require_decision_snapshot", False)
    if not isinstance(required, bool):
        raise ValueError("evidence policy require_decision_snapshot must be a boolean")
    if not required:
        return []

    decision = read_text(DECISION_FILE, "")
    marker = f"## {SNAPSHOT_HEADING}"
    parts = decision.split(marker, 1)
    if len(parts) != 2:
        return ["Decision Record must include an Evidence Snapshot"]
    section = parts[1].split("\n## ", 1)[0]
    match = _DIGEST_PATTERN.search(section)
    if not match:
        return ["Decision Record Evidence Snapshot must include a SHA-256 input digest"]
    expected = decision_input_digest()
    if match.group(0).lower() != expected:
        return ["Decision Record Evidence Snapshot is stale; regenerate or review the decision"]
    return []
