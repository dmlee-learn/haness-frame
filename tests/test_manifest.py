from __future__ import annotations

import contextlib
import io
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

from haness_frame_app.templates.runtime import manifest, storage


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "existing.txt").write_text("content", encoding="utf-8")
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(manifest, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_manifest(self, payload: object) -> None:
        (self.root / "workspace" / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_valid_manifest_checks_regular_project_files(self) -> None:
        self.write_manifest({"project_name": "test", "format_version": "1.0", "files": ["existing.txt"]})
        report = manifest.validate_manifest()
        self.assertTrue(report["valid"])
        self.assertEqual((report["checked_files"], report["declared_files"]), (1, 1))

    def test_missing_or_malformed_manifest_is_invalid(self) -> None:
        missing = manifest.validate_manifest()
        self.assertFalse(missing["valid"])
        path = self.root / "workspace" / "manifest.json"
        path.write_text('{"secret-value":', encoding="utf-8")
        malformed = manifest.validate_manifest()
        self.assertFalse(malformed["valid"])
        self.assertIn("invalid JSON at line", malformed["issues"][0])
        self.assertNotIn("secret-value", malformed["issues"][0])

    def test_manifest_requires_metadata_and_nonempty_file_list(self) -> None:
        self.write_manifest({"files": []})
        report = manifest.validate_manifest()
        self.assertFalse(report["valid"])
        self.assertIn("manifest project_name must be a non-empty string", report["issues"])
        self.assertIn("manifest format_version must be a non-empty string", report["issues"])
        self.assertIn("manifest files must not be empty", report["issues"])

    def test_manifest_print_command_returns_nonzero_for_invalid_report(self) -> None:
        self.write_manifest({"project_name": "test", "format_version": "1.0", "files": []})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = manifest.print_manifest_report()
        self.assertEqual(return_code, 1)
        self.assertFalse(json.loads(output.getvalue())["valid"])

    def test_unsafe_duplicate_and_directory_entries_are_rejected(self) -> None:
        (self.root / "folder").mkdir()
        self.write_manifest(
            {
                "project_name": "test",
                "format_version": "1.0",
                "files": ["existing.txt", "existing.txt", "../outside.txt", "C:/outside.txt", "folder"],
            }
        )
        report = manifest.validate_manifest()
        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicate" in issue for issue in report["issues"]))
        self.assertEqual(sum("unsafe" in issue for issue in report["issues"]), 2)
        self.assertTrue(any("missing manifest file: folder" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
