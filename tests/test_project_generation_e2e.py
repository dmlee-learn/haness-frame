from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app import project_docs


class ProjectGenerationE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "generated-project"
        with (
            patch.object(project_docs, "project_dir", return_value=self.project),
            patch.object(project_docs, "default_project_settings", return_value={"role_assignments": {}}),
            patch.object(
                project_docs,
                "project_service_snapshot",
                return_value={"role_services": {}, "fallback_service": {}},
            ),
        ):
            base, self.created, self.skipped = project_docs.create_project_files(
                "generated-project",
                "증거와 claim gate를 검증하는 샘플 프로그램",
                "A sample program that verifies evidence and claim gates.",
                False,
            )
        self.assertEqual(base, self.project)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_app(self, *args: str, expected_code: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, "app.py", *args],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, expected_code, completed.stderr)
        return completed

    def add_evidence(self, *, url: str, title: str) -> None:
        self.run_app(
            "add-evidence",
            "--query",
            title,
            "--provider",
            "fixture",
            "--url",
            url,
            "--title",
            title,
            "--excerpt",
            "This fixture excerpt is long enough to satisfy evidence validation.",
            "--confidence",
            "high",
            "--why-it-matters",
            "It supports the generated project decision.",
            "--recommended-use",
            "Use this source in the accepted decision.",
        )

    def test_project_readme_follows_request_language(self) -> None:
        korean_project = Path(self.temp_dir.name) / "korean-project"
        english_project = Path(self.temp_dir.name) / "english-project"
        with (
            patch.object(project_docs, "project_dir", return_value=korean_project),
            patch.object(project_docs, "default_project_settings", return_value={"role_assignments": {}}),
            patch.object(
                project_docs,
                "project_service_snapshot",
                return_value={"role_services": {}, "fallback_service": {}},
            ),
        ):
            project_docs.create_project_files("korean-project", "테스트가 있는 계산기 만들기", "", False)
        self.assertTrue((korean_project / "README.md").is_file())
        self.assertTrue((korean_project / "README.ko.md").is_file())
        korean_manifest = json.loads((korean_project / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("README.ko.md", korean_manifest["files"])
        self.assertIn("한 줄 구현", (korean_project / "README.ko.md").read_text(encoding="utf-8"))

        with (
            patch.object(project_docs, "project_dir", return_value=english_project),
            patch.object(project_docs, "default_project_settings", return_value={"role_assignments": {}}),
            patch.object(
                project_docs,
                "project_service_snapshot",
                return_value={"role_services": {}, "fallback_service": {}},
            ),
        ):
            project_docs.create_project_files("english-project", "Create a calculator with tests", "", False)
        self.assertTrue((english_project / "README.md").is_file())
        self.assertFalse((english_project / "README.ko.md").exists())
        self.assertFalse((english_project / "README.en.md").exists())
        english_manifest = json.loads((english_project / "workspace" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("README.ko.md", english_manifest["files"])

    def test_generated_project_opens_gate_after_evidence_claim_and_decision(self) -> None:
        self.assertGreater(self.created, 40)
        self.assertEqual(self.skipped, 0)
        policy = json.loads((self.project / "workspace" / "evidence-policy.json").read_text(encoding="utf-8"))
        self.assertTrue(policy["require_claim_matrix"])
        self.assertTrue(policy["require_decision_snapshot"])
        orchestration_policy = json.loads(
            (self.project / "workspace" / "orchestration-policy.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(orchestration_policy["max_ai_calls"], orchestration_policy["max_roles"])
        self.assertGreaterEqual(orchestration_policy["max_debate_ai_calls"], orchestration_policy["max_roles"])
        self.assertGreaterEqual(orchestration_policy["max_debate_elapsed_seconds"], 1)
        self.assertGreaterEqual(orchestration_policy["max_debate_rounds"], 1)
        self.assertLess(orchestration_policy["min_output_chars"], orchestration_policy["max_output_chars"])
        self.assertTrue((self.project / "src" / "harness_app" / "claims.py").is_file())
        self.assertTrue((self.project / "src" / "harness_app" / "provenance.py").is_file())
        self.assertTrue((self.project / "src" / "harness_app" / "orchestration_policy.py").is_file())

        manifest = json.loads(self.run_app("manifest").stdout)
        self.assertTrue(manifest["valid"], manifest["issues"])
        initial_gate = json.loads(self.run_app("gate", expected_code=1).stdout)
        self.assertFalse(initial_gate["allowed"])
        self.assertTrue(any("structured claim" in issue for issue in initial_gate["issues"]))

        support_url = "https://example.com/generated-support"
        self.add_evidence(url=support_url, title="Generated support")
        self.add_evidence(url="https://example.org/generated-test", title="Generated test evidence")
        claim = json.loads(
            self.run_app(
                "claim-add",
                "--claim",
                "The generated project workflow is evidence gated.",
                "--support-url",
                support_url,
                "--confidence",
                "high",
            ).stdout
        )
        self.assertTrue(str(claim["claim_id"]).startswith("claim-"))
        self.run_app("decision-draft")

        evidence_report = json.loads(self.run_app("evidence-check").stdout)
        self.assertTrue(evidence_report["valid"], evidence_report["issues"])
        evidence_markdown = self.project / "research" / "search-evidence.md"
        evidence_markdown.write_text("stale generated view\n", encoding="utf-8")
        stale_view = json.loads(self.run_app("evidence-check", expected_code=1).stdout)
        self.assertEqual(stale_view["derivative"]["status"], "stale")
        rebuilt = json.loads(self.run_app("evidence-rebuild").stdout)
        self.assertEqual(rebuilt["record_count"], 2)
        self.assertTrue(json.loads(self.run_app("evidence-check").stdout)["valid"])
        final_gate = json.loads(self.run_app("gate").stdout)
        self.assertTrue(final_gate["allowed"], final_gate["issues"])
        decision = (self.project / "docs" / "03-decision-record.md").read_text(encoding="utf-8")
        self.assertIn(str(claim["claim_id"]), decision)
        self.assertIn("## Evidence Snapshot", decision)

        evidence_path = self.project / "workspace" / "evidence" / "search-evidence.json"
        records = json.loads(evidence_path.read_text(encoding="utf-8"))
        records[0]["excerpt"] += " Materially changed after approval."
        evidence_path.write_text(json.dumps(records), encoding="utf-8")
        stale_gate = json.loads(self.run_app("gate", expected_code=1).stdout)
        self.assertFalse(stale_gate["allowed"])
        self.assertTrue(any("Snapshot is stale" in issue for issue in stale_gate["issues"]))


if __name__ == "__main__":
    unittest.main()
