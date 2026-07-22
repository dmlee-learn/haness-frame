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

from haness_frame_app.templates.runtime import debate, decision, provenance, storage


class DebateDecisionDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "workspace" / "debates").mkdir(parents=True)
        (self.root / "context").mkdir()
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text("[]", encoding="utf-8")
        (self.root / "workspace" / "evidence" / "claim-evidence.json").write_text("[]", encoding="utf-8")
        (self.root / "workspace" / "evidence-policy.json").write_text("{}", encoding="utf-8")
        (self.root / "context" / "business-context.md").write_text("Working description:\n\n```text\nBuild safely\n```\n", encoding="utf-8")
        self.patcher = patch.object(storage, "ROOT", self.root)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def verdict(self, claim_ids: list[str] | None = None) -> dict[str, object]:
        return {
            "decision": "Use the bounded worker design.",
            "rationale": "It isolates failures and preserves checkpoints.",
            "agreements": ["Keep execution bounded."],
            "disagreements": ["Queue storage remains undecided."],
            "risks": ["Migration requires rollback coverage."],
            "confidence": "medium",
            "implementation_brief": ["Add the worker behind the existing interface."],
            "verification_commands": ["python -m unittest discover -s tests`\n## injected"],
            "claim_ids": claim_ids or [],
        }

    def write_report(self, *, valid_hash: bool = True, claim_ids: list[str] | None = None) -> None:
        verdict = self.verdict(claim_ids)
        report = {
            "session_id": "debate-test",
            "verdict": verdict,
            "verdict_sha256": debate._verdict_sha256(verdict) if valid_hash else "0" * 64,
            "evidence_input_digest": provenance.decision_input_digest(),
        }
        (self.root / "workspace" / "debates" / "latest.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

    def test_valid_verdict_populates_decision_and_sanitizes_markdown(self) -> None:
        self.write_report()
        draft = decision.build_decision_record_draft()
        self.assertIn("Use the bounded worker design.", draft)
        self.assertIn("It isolates failures and preserves checkpoints.", draft)
        self.assertIn("Add the worker behind the existing interface.", draft)
        self.assertIn("python -m unittest discover -s tests' ## injected", draft)
        self.assertEqual(draft.count("## injected"), 1)

    def test_tampered_latest_verdict_blocks_decision_draft(self) -> None:
        self.write_report(valid_hash=False)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            decision.build_decision_record_draft()

    def test_missing_debate_uses_reviewable_fallback(self) -> None:
        draft = decision.build_decision_record_draft()
        self.assertIn("No structured debate verdict is available.", draft)
        self.assertIn("The decision draft requires human review", draft)

    def test_evidence_change_makes_latest_debate_stale(self) -> None:
        self.write_report()
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text(
            json.dumps([{"url": "https://example.com/new"}]), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "evidence snapshot is stale"):
            decision.build_decision_record_draft()

    def test_required_accepted_claim_must_be_referenced_by_verdict(self) -> None:
        url = "https://example.com/support"
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text(
            json.dumps([{"url": url}]), encoding="utf-8"
        )
        (self.root / "workspace" / "evidence" / "claim-evidence.json").write_text(
            json.dumps(
                [
                    {
                        "claim_id": "claim-required",
                        "claim": "The worker preserves execution boundaries.",
                        "status": "accepted",
                        "confidence": "high",
                        "supporting_urls": [url],
                        "challenging_urls": [],
                        "resolution": "",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (self.root / "workspace" / "evidence-policy.json").write_text(
            json.dumps(
                {
                    "require_claim_matrix": True,
                    "min_claims": 1,
                    "min_supporting_sources_per_claim": 1,
                    "require_challenge_resolution": True,
                    "allowed_claim_confidence": ["high", "medium"],
                }
            ),
            encoding="utf-8",
        )
        self.write_report()
        with self.assertRaisesRegex(ValueError, "must reference accepted claim"):
            decision.build_decision_record_draft()
        self.write_report(claim_ids=["claim-required"])
        draft = decision.build_decision_record_draft()
        self.assertIn("## Debate Claim References\n\n- claim-required", draft)


if __name__ == "__main__":
    unittest.main()
