from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import archive, audit, storage


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=value\n", encoding="utf-8")
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.policy = {
            "max_files": 100,
            "max_file_bytes": 10000,
            "max_total_bytes": 100000,
            "exclude_globs": [
                ".git/*",
                "workspace/archives/*",
                "workspace/.locks/*",
                "workspace/.operations/*",
                "**/.*.tmp",
                "__pycache__/*",
                "**/__pycache__/*",
                "*.pyc",
                ".env",
                "*.key",
                "*.pem",
            ],
        }
        self.write_policy()
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(archive, "ROOT", self.root),
            patch.object(archive, "WORKSPACE", self.root / "workspace"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_policy(self) -> None:
        (self.root / "workspace" / "archive-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")

    def test_archive_includes_project_file_and_excludes_secrets_and_cache(self) -> None:
        cache = self.root / "src" / "__pycache__"
        cache.mkdir()
        (cache / "app.pyc").write_bytes(b"cache")
        locks = self.root / "workspace" / ".locks"
        locks.mkdir()
        (locks / "active.lock").write_text("pid=1", encoding="utf-8")
        (self.root / "src" / ".app.py.partial.tmp").write_text("partial", encoding="utf-8")
        archive_path = archive.create_archive("safe export")
        with zipfile.ZipFile(archive_path) as bundle:
            names = bundle.namelist()
            manifest = json.loads(bundle.read(archive.ARCHIVE_MANIFEST))
        prefix = f"{self.root.name}/"
        self.assertIn(f"{prefix}src/app.py", names)
        self.assertNotIn(f"{prefix}.env", names)
        self.assertFalse(any("__pycache__" in name for name in names))
        self.assertFalse(any("/.locks/" in name or name.endswith(".tmp") for name in names))
        self.assertEqual(manifest["format"], "haness-frame-archive")
        self.assertEqual(manifest["file_count"], len(names) - 1)
        self.assertTrue(archive.verify_archive(archive_path)["valid"])

    def test_archive_skips_symlink_to_file_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "outside.txt"
            outside.write_text("private\n", encoding="utf-8")
            link = self.root / "src" / "outside-link.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            archive_path = archive.create_archive()
            with zipfile.ZipFile(archive_path) as bundle:
                self.assertFalse(any(name.endswith("outside-link.txt") for name in bundle.namelist()))

    def test_policy_limit_fails_before_partial_zip_is_created(self) -> None:
        self.policy["max_file_bytes"] = 1000
        self.write_policy()
        (self.root / "src" / "large.bin").write_bytes(b"x" * 1001)
        with self.assertRaisesRegex(ValueError, "max_file_bytes"):
            archive.create_archive()
        archive_dir = self.root / "workspace" / "archives"
        self.assertEqual(list(archive_dir.glob("*.zip")), [])

    def test_verify_latest_detects_modified_member(self) -> None:
        archive_path = archive.create_archive()
        with zipfile.ZipFile(archive_path, "a") as bundle:
            bundle.writestr(f"{self.root.name}/src/extra.py", "changed = True\n")
        report = archive.verify_archive()
        self.assertFalse(report["valid"])
        self.assertTrue(any("missing from manifest" in issue for issue in report["issues"]))

    def test_verify_rejects_unsafe_member_path(self) -> None:
        archive_path = archive.create_archive()
        with zipfile.ZipFile(archive_path, "a") as bundle:
            bundle.writestr("../outside.txt", "unsafe\n")
        report = archive.verify_archive(archive_path)
        self.assertFalse(report["valid"])
        self.assertTrue(any("unsafe member paths" in issue for issue in report["issues"]))

    def test_verify_detects_content_hash_mismatch(self) -> None:
        archive_path = archive.create_archive()
        rewritten = archive_path.with_suffix(".rewritten.zip")
        target = f"{self.root.name}/src/app.py"
        with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(rewritten, "w") as destination:
            for info in source.infolist():
                payload = b"value = 2\r\n" if info.filename == target else source.read(info)
                destination.writestr(info.filename, payload)
        report = archive.verify_archive(rewritten)
        self.assertFalse(report["valid"])
        self.assertTrue(any("hash mismatch" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
