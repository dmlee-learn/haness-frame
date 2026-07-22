from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import provenance, storage


class DecisionProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "docs").mkdir()
        self.evidence_path = self.root / provenance.EVIDENCE_FILE
        self.evidence_path.write_text(json.dumps([{"url": "https://example.com", "excerpt": "original"}]), encoding="utf-8")
        (self.root / provenance.CLAIMS_FILE).write_text(json.dumps([{"claim_id": "claim-1"}]), encoding="utf-8")
        self.policy_path = self.root / "workspace" / "evidence-policy.json"
        self.policy_path.write_text(json.dumps({"require_decision_snapshot": True}), encoding="utf-8")
        self.patcher = patch.object(storage, "ROOT", self.root)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_matching_snapshot_is_valid_until_evidence_changes(self) -> None:
        digest = provenance.decision_input_digest()
        (self.root / provenance.DECISION_FILE).write_text(
            f"# Decision\n\n## Evidence Snapshot\n\n- input_digest: `{digest}`\n",
            encoding="utf-8",
        )
        self.assertEqual(provenance.decision_snapshot_issues(), [])
        self.evidence_path.write_text(json.dumps([{"url": "https://example.com", "excerpt": "changed"}]), encoding="utf-8")
        self.assertIn("stale", provenance.decision_snapshot_issues()[0])

    def test_missing_snapshot_is_rejected_when_required(self) -> None:
        (self.root / provenance.DECISION_FILE).write_text("# Decision\n", encoding="utf-8")
        self.assertIn("must include", provenance.decision_snapshot_issues()[0])

    def test_disabled_policy_preserves_existing_decisions(self) -> None:
        self.policy_path.write_text(json.dumps({"require_decision_snapshot": False}), encoding="utf-8")
        self.assertEqual(provenance.decision_snapshot_issues(), [])

    def test_policy_value_must_be_boolean(self) -> None:
        self.policy_path.write_text(json.dumps({"require_decision_snapshot": "yes"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            provenance.decision_snapshot_issues()


if __name__ == "__main__":
    unittest.main()
