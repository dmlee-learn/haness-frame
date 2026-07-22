from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, patching, storage


class PatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "workspace" / "repair-policy.json").write_text(
            json.dumps(
                {
                    "editable_roots": ["src", "tests", "implementation"],
                    "max_patch_files": 5,
                    "max_patch_bytes": 10000,
                }
            ),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(patching, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_rejects_path_traversal(self) -> None:
        diff = "--- a/src/a.py\n+++ b/src/../../outside.py\n@@ -1 +1 @@\n-old\n+new\n"
        with self.assertRaisesRegex(ValueError, "escapes the project"):
            patching.patch_plan(diff)

    def test_repair_policy_rejects_non_boolean_reviewer_requirement(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["require_independent_reviewer_service"] = "yes"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            patching.load_repair_policy()

    def test_rejects_path_outside_editable_roots(self) -> None:
        (self.root / "README.md").write_text("old\n", encoding="utf-8")
        diff = "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n"
        with self.assertRaisesRegex(ValueError, "outside editable roots"):
            patching.patch_plan(diff)

    def test_nested_editable_root_does_not_allow_siblings(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["editable_roots"] = ["src/allowed"]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        (self.root / "src" / "other").mkdir()
        (self.root / "src" / "other" / "sample.py").write_text("old\n", encoding="utf-8")
        diff = "--- a/src/other/sample.py\n+++ b/src/other/sample.py\n@@ -1 +1 @@\n-old\n+new\n"

        with self.assertRaisesRegex(ValueError, "outside editable roots"):
            patching.patch_plan(diff)

    def test_rejects_context_mismatch_without_writing(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_text("actual\n", encoding="utf-8")
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-expected\n+changed\n"
        with self.assertRaisesRegex(ValueError, "context mismatch"):
            patching.patch_plan(diff)
        self.assertEqual(target.read_text(encoding="utf-8"), "actual\n")

    def test_apply_and_rollback_preserve_record(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_text("value = 1\n", encoding="utf-8")
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"

        with patch.object(patching, "enforce_decision_gate"):
            metadata = patching.apply_patch_text(diff)

        self.assertEqual(target.read_text(encoding="utf-8"), "value = 2\n")
        self.assertEqual(patching.patch_state(str(metadata["patch_id"]))["state"], "applied")
        rolled_back = patching.rollback_patch(str(metadata["patch_id"]))
        self.assertTrue(rolled_back["rolled_back"])
        self.assertEqual(patching.patch_state(str(metadata["patch_id"]))["state"], "rolled_back")
        self.assertEqual(target.read_text(encoding="utf-8"), "value = 1\n")

    def test_rollback_refuses_to_overwrite_later_changes(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_text("value = 1\n", encoding="utf-8")
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        with patch.object(patching, "enforce_decision_gate"):
            metadata = patching.apply_patch_text(diff)
        target.write_text("user change\n", encoding="utf-8")

        state = patching.patch_state(str(metadata["patch_id"]))
        self.assertEqual(state["state"], "conflict")
        self.assertEqual(state["conflicts"], ["src/sample.py"])
        with self.assertRaisesRegex(ValueError, "rollback conflict"):
            patching.rollback_patch(str(metadata["patch_id"]))
        self.assertEqual(target.read_text(encoding="utf-8"), "user change\n")

    def test_same_size_patch_advances_timestamp_for_bytecode_invalidation(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_text("value = 1\n", encoding="utf-8")
        os.utime(target, (100.75, 100.75))
        before_second = int(target.stat().st_mtime)
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        with patch.object(patching, "enforce_decision_gate"):
            patching.apply_patch_text(diff)
        self.assertGreater(int(target.stat().st_mtime), before_second)

    def test_patch_preserves_crlf_source_with_lf_diff(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_bytes(b"first\r\nvalue = 1\r\n")
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1,2 +1,2 @@\n first\n-value = 1\n+value = 2\n"
        with patch.object(patching, "enforce_decision_gate"):
            patching.apply_patch_text(diff)
        self.assertEqual(target.read_bytes(), b"first\r\nvalue = 2\r\n")

    def test_patch_accepts_crlf_diff_and_windows_style_headers(self) -> None:
        target = self.root / "src" / "sample.py"
        target.write_bytes(b"value = 1\n")
        diff = "--- a\\src\\sample.py\r\n+++ b\\src\\sample.py\r\n@@ -1 +1 @@\r\n-value = 1\r\n+value = 2\r\n"
        with patch.object(patching, "enforce_decision_gate"):
            patching.apply_patch_text(diff)
        self.assertEqual(target.read_bytes(), b"value = 2\n")


if __name__ == "__main__":
    unittest.main()
