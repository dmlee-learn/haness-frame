from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import implementation, repair


class ImplementationWorkflowTests(unittest.TestCase):
    def test_normalize_unified_diff_repairs_hunk_counts(self) -> None:
        malformed = """--- /dev/null
+++ b/implementation/example.py
@@ -0,0 +1,99 @@
+first
+second
"""
        normalized = repair.normalize_unified_diff_hunks(malformed)
        self.assertIn("@@ -0,0 +1,2 @@", normalized)

    def test_rejected_verification_plan_stops_before_coder(self) -> None:
        with (
            patch.object(implementation, "enforce_decision_gate"),
            patch.object(implementation, "verification_plan", return_value={"approved": False}),
            patch.object(implementation, "invoke_cached") as coder,
        ):
            report = implementation.implement_project("Build a calculator")

        self.assertEqual(report["status"], "blocked")
        coder.assert_not_called()

    def test_successful_implementation_runs_finish(self) -> None:
        diff = "--- /dev/null\n+++ b/implementation/example.py\n@@ -0,0 +1,1 @@\n+value = 1\n"
        with (
            patch.object(implementation, "enforce_decision_gate"),
            patch.object(implementation, "verification_plan", return_value={"approved": True}),
            patch.object(implementation, "load_repair_policy", return_value={"editable_roots": [], "ai_max_tokens": 1024}),
            patch.object(implementation, "read_text", return_value="accepted"),
            patch.object(implementation, "invoke_cached", return_value={"content": f"```diff\n{diff}```"}),
            patch.object(implementation, "write_text", return_value=Path("workspace/candidate.diff")),
            patch.object(implementation, "patch_plan_report", return_value={"valid": True}),
            patch.object(implementation, "create_snapshot", return_value={"name": "before"}),
            patch.object(implementation, "apply_patch_text", return_value={"patch_id": "patch-one"}),
            patch.object(implementation, "finish_project", return_value={"status": "completed"}),
            patch.object(implementation, "decision_gate", return_value={"allowed": True}),
        ):
            report = implementation.implement_project("Build a calculator", max_tokens=512)

        self.assertEqual(report["status"], "completed")
        self.assertNotIn("rollback", report)

    def test_failed_finish_rolls_back_applied_patch(self) -> None:
        diff = "--- /dev/null\n+++ b/implementation/example.py\n@@ -0,0 +1,1 @@\n+value = 1\n"
        with (
            patch.object(implementation, "enforce_decision_gate"),
            patch.object(implementation, "verification_plan", return_value={"approved": True}),
            patch.object(implementation, "load_repair_policy", return_value={"editable_roots": [], "ai_max_tokens": 1024}),
            patch.object(implementation, "read_text", return_value="accepted"),
            patch.object(implementation, "invoke_cached", return_value={"content": diff}),
            patch.object(implementation, "write_text", return_value=Path("workspace/candidate.diff")),
            patch.object(implementation, "patch_plan_report", return_value={"valid": True}),
            patch.object(implementation, "create_snapshot", return_value={"name": "before"}),
            patch.object(implementation, "apply_patch_text", return_value={"patch_id": "patch-one"}),
            patch.object(implementation, "finish_project", return_value={"status": "blocked"}),
            patch.object(implementation, "decision_gate", return_value={"allowed": True}),
            patch.object(implementation, "rollback_patch", return_value={"rolled_back": True}) as rollback,
        ):
            report = implementation.implement_project("Build a calculator")

        self.assertEqual(report["status"], "rolled_back")
        rollback.assert_called_once_with("patch-one")


if __name__ == "__main__":
    unittest.main()
