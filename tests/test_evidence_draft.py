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

from haness_frame_app.templates.runtime import audit, engine, evidence, storage


class EvidenceDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "research").mkdir(parents=True)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text("[]", encoding="utf-8")
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(engine, "ROOT", self.root),
            patch.object(evidence, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def draft() -> str:
        return """# Search Evidence Draft

## 1. Source heading

- query: harness verification
- provider: manual
- url: https://example.com/source
- title: Primary Source
- excerpt: This evidence contains enough detail for validation.
- retrieved_at: 2026-07-19T00:00:00+00:00
- confidence: high
- why_it_matters: It defines the expected behavior.
- recommended_use: Cite it in the decision record.
"""

    def test_commit_parses_complete_draft_from_project_root(self) -> None:
        path = self.root / "research" / "search-evidence-draft.md"
        path.write_text(self.draft(), encoding="utf-8")
        result = evidence.commit_evidence_draft("research/search-evidence-draft.md")
        self.assertEqual(result["total"], 1)
        records = json.loads((self.root / evidence.EVIDENCE_JSON).read_text(encoding="utf-8"))
        self.assertEqual(records[0]["title"], "Primary Source")

    def test_commit_rejects_draft_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "outside.md"
            outside.write_text(self.draft(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inside the project"):
                evidence.commit_evidence_draft(str(outside))

    def test_commit_rejects_missing_required_field(self) -> None:
        path = self.root / "research" / "search-evidence-draft.md"
        path.write_text(self.draft().replace("- confidence: high", "- confidence: "), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "confidence"):
            evidence.commit_evidence_draft("research/search-evidence-draft.md")

    def test_corrupt_evidence_is_reported_and_preserved_on_mutation(self) -> None:
        path = self.root / evidence.EVIDENCE_JSON
        original = '[{"query":"secret"},]'
        path.write_text(original, encoding="utf-8")
        report = evidence.evidence_policy_report()
        self.assertFalse(report["valid"])
        self.assertIn("invalid JSON at line", report["issues"][0])
        self.assertNotIn("secret", report["issues"][0])
        with self.assertRaisesRegex(ValueError, "contains invalid JSON"):
            evidence.add_evidence(
                query="q",
                provider="manual",
                url="https://example.com/new",
                title="New",
                excerpt="A sufficiently detailed evidence excerpt.",
                confidence="high",
                why_it_matters="It matters.",
                recommended_use="Use it.",
            )
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_non_object_evidence_record_is_rejected(self) -> None:
        path = self.root / evidence.EVIDENCE_JSON
        path.write_text('[{"query":"valid object"}, "invalid"]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-object record"):
            evidence.load_evidence()

    def test_stale_markdown_is_detected_and_rebuilt_from_json(self) -> None:
        evidence.save_evidence(
            [
                {
                    "query": "q",
                    "provider": "manual",
                    "url": "https://example.com/source",
                    "title": "Source",
                    "excerpt": "A sufficiently detailed evidence excerpt.",
                    "retrieved_at": "2026-07-19T00:00:00+00:00",
                    "confidence": "high",
                    "why_it_matters": "It defines behavior.",
                    "recommended_use": "Use it in the decision.",
                }
            ]
        )
        markdown_path = self.root / evidence.EVIDENCE_MD
        markdown_path.write_text("stale\n", encoding="utf-8")
        stale = evidence.evidence_derivative_report()
        self.assertFalse(stale["valid"])
        self.assertIn("evidence-rebuild", stale["issues"][0])
        rebuilt = evidence.rebuild_evidence_markdown()
        self.assertEqual(rebuilt["record_count"], 1)
        self.assertTrue(evidence.evidence_derivative_report()["valid"])

    def test_json_remains_authoritative_when_markdown_write_fails(self) -> None:
        records = [
            {
                "query": "q",
                "provider": "manual",
                "url": "https://example.com/committed",
                "title": "Committed",
                "excerpt": "A sufficiently detailed evidence excerpt.",
                "retrieved_at": "2026-07-19T00:00:00+00:00",
                "confidence": "high",
                "why_it_matters": "It verifies commit ordering.",
                "recommended_use": "Use it for recovery testing.",
            }
        ]
        real_write = evidence.write_text

        def fail_markdown(path: str, content: str) -> Path:
            if path == evidence.EVIDENCE_MD:
                raise OSError("injected Markdown failure")
            return real_write(path, content)

        with patch.object(evidence, "write_text", side_effect=fail_markdown):
            with self.assertRaisesRegex(RuntimeError, "structured evidence was saved"):
                evidence.save_evidence(records)
        committed = json.loads((self.root / evidence.EVIDENCE_JSON).read_text(encoding="utf-8"))
        self.assertEqual(committed[0]["url"], "https://example.com/committed")

    def test_corrupt_search_plan_blocks_evidence_report(self) -> None:
        plan = self.root / evidence.SEARCH_PLAN_JSON
        plan.write_text('{"searches": [}', encoding="utf-8")
        report = evidence.evidence_policy_report()
        self.assertFalse(report["valid"])
        self.assertIn("search-plan.json contains invalid JSON", report["issues"][0])

    def test_corrupt_evidence_closes_decision_gate_without_raising(self) -> None:
        path = self.root / evidence.EVIDENCE_JSON
        path.write_text('{"not":"a list"}', encoding="utf-8")
        gate = engine.decision_gate()
        self.assertFalse(gate["allowed"])
        self.assertTrue(any("root must be a JSON list" in issue for issue in gate["issues"]))


if __name__ == "__main__":
    unittest.main()
