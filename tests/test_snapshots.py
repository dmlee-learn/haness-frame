from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, snapshots, storage


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "context").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "context" / "value.txt").write_text("original\n", encoding="utf-8")
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(snapshots, "ROOT", self.root),
            patch.object(snapshots, "WORKSPACE", self.root / "workspace"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_restore_replaces_captured_files_and_preserves_snapshot_history(self) -> None:
        metadata = snapshots.create_snapshot("before change")
        target = self.root / "context" / "value.txt"
        target.write_text("changed\n", encoding="utf-8")
        extra = self.root / "context" / "extra.txt"
        extra.write_text("later\n", encoding="utf-8")

        result = snapshots.restore_snapshot(str(metadata["name"]))

        self.assertIn("context", result["restored"])
        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        self.assertFalse(extra.exists())
        self.assertEqual([item["name"] for item in snapshots.list_snapshots()], [metadata["name"]])

    def test_restore_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "escapes"):
            snapshots.restore_snapshot("../outside")

    def test_restore_removes_temporary_copy(self) -> None:
        metadata = snapshots.create_snapshot("cleanup")
        restore_temp = self.root / "restore-temp"
        with patch.object(snapshots.tempfile, "mkdtemp", return_value=str(restore_temp)):
            snapshots.restore_snapshot(str(metadata["name"]))
        self.assertFalse(restore_temp.exists())


if __name__ == "__main__":
    unittest.main()
