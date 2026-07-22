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

from haness_frame_app.templates.runtime import audit, claims, evidence, storage


class ClaimEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "docs").mkdir()
        self.urls = ["https://example.com/support", "https://example.org/challenge"]
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text(
            json.dumps([{"url": url} for url in self.urls]),
            encoding="utf-8",
        )
        (self.root / "workspace" / "evidence" / "claim-evidence.json").write_text("[]", encoding="utf-8")
        (self.root / "workspace" / "evidence-policy.json").write_text(
            json.dumps(
                {
                    "require_claim_matrix": True,
                    "min_claims": 1,
                    "min_supporting_sources_per_claim": 1,
                    "require_challenge_resolution": True,
                    "allowed_claim_confidence": ["high", "medium"],
                    "min_records": 1,
                    "min_distinct_urls": 1,
                    "allowed_confidence": ["high", "medium"],
                    "min_excerpt_chars": 1,
                }
            ),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_supported_claim_passes_and_decision_must_reference_it(self) -> None:
        record = claims.add_claim(
            claim="The selected API contract is backward compatible.",
            supporting_urls=[self.urls[0]],
            confidence="high",
        )
        self.assertTrue(claims.claim_policy_report()["valid"])
        (self.root / "docs" / "03-decision-record.md").write_text("# Decision\n", encoding="utf-8")
        self.assertIn(str(record["claim_id"]), claims.decision_claim_issues()[0])
        (self.root / "docs" / "03-decision-record.md").write_text(
            f"# Decision\n\n## Claims Accepted\n\n- {record['claim_id']}\n",
            encoding="utf-8",
        )
        self.assertEqual(claims.decision_claim_issues(), [])

    def test_unknown_evidence_url_is_rejected_without_saving_claim(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            claims.add_claim(
                claim="An unsupported statement.",
                supporting_urls=["https://unknown.example/source"],
            )
        self.assertEqual(claims.load_claims(), [])

    def test_challenging_source_requires_substantive_resolution(self) -> None:
        with self.assertRaisesRegex(ValueError, "challenge resolution"):
            claims.add_claim(
                claim="The migration can proceed safely.",
                supporting_urls=[self.urls[0]],
                challenging_urls=[self.urls[1]],
                resolution="too short",
            )
        record = claims.add_claim(
            claim="The migration can proceed with the documented rollback.",
            supporting_urls=[self.urls[0]],
            challenging_urls=[self.urls[1]],
            resolution="The rollback fixture directly addresses the reported migration risk.",
        )
        self.assertEqual(record["status"], "accepted")

    def test_required_empty_matrix_blocks_combined_evidence_status(self) -> None:
        ok, issues = evidence.evidence_status()
        self.assertFalse(ok)
        self.assertTrue(any("structured claim" in issue for issue in issues))

    def test_malformed_claim_json_is_reported(self) -> None:
        (self.root / "workspace" / "evidence" / "claim-evidence.json").write_text("not-json", encoding="utf-8")
        report = claims.claim_policy_report()
        self.assertFalse(report["valid"])
        self.assertTrue(any("invalid JSON" in issue for issue in report["issues"]))

    def test_policy_error_does_not_leave_partially_added_claim(self) -> None:
        policy_path = self.root / "workspace" / "evidence-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["require_claim_matrix"] = "yes"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            claims.add_claim(
                claim="This claim must not be persisted.",
                supporting_urls=[self.urls[0]],
            )
        self.assertEqual(claims.load_claims(), [])


if __name__ == "__main__":
    unittest.main()
