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

from haness_frame_app.templates.runtime import audit, storage


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
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

    def test_check_summarizes_valid_records(self) -> None:
        audit.log_event("repair.started", session_id="one")
        audit.log_event("repair.completed", session_id="one")
        report = audit.audit_check()
        self.assertTrue(report["valid"])
        self.assertEqual(report["record_count"], 2)
        self.assertEqual(report["event_counts"]["repair.started"], 1)

    def test_hash_chain_detects_valid_json_record_tampering(self) -> None:
        audit.log_event("first.event", value="original")
        audit.log_event("second.event", value="stable")
        path = self.root / audit.AUDIT_LOG
        lines = path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["value"] = "tampered"
        lines[0] = json.dumps(first)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = audit.audit_check()
        self.assertFalse(report["valid"])
        self.assertTrue(any("record hash mismatch" in issue for issue in report["issues"]))

    def test_first_chained_event_anchors_legacy_prefix(self) -> None:
        path = self.root / audit.AUDIT_LOG
        path.parent.mkdir(parents=True)
        legacy = {"created_at": "2026-01-01T00:00:00+00:00", "event": "legacy.event", "value": "original"}
        path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        audit.log_event("chained.event")
        self.assertTrue(audit.audit_check()["valid"])
        lines = path.read_text(encoding="utf-8").splitlines()
        changed = json.loads(lines[0])
        changed["value"] = "tampered"
        lines[0] = json.dumps(changed)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = audit.audit_check()
        self.assertFalse(report["valid"])
        self.assertTrue(any("previous hash mismatch" in issue for issue in report["issues"]))

    def test_check_reports_unchained_record_inserted_after_chain_start(self) -> None:
        audit.log_event("first.event")
        path = self.root / audit.AUDIT_LOG
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"created_at": "2026-01-01T00:00:00+00:00", "event": "inserted"}) + "\n")
        audit.log_event("second.event")
        report = audit.audit_check()
        self.assertFalse(report["valid"])
        self.assertTrue(any("unchained record" in issue for issue in report["issues"]))

    def test_caller_cannot_override_hash_chain_fields(self) -> None:
        record = audit.log_event(
            "protected.event",
            format_version=1,
            created_at="invalid",
            previous_sha256="forged",
            record_sha256="forged",
        )
        self.assertEqual(record["format_version"], audit.AUDIT_FORMAT_VERSION)
        self.assertNotEqual(record["created_at"], "invalid")
        self.assertNotEqual(record["previous_sha256"], "forged")
        self.assertNotEqual(record["record_sha256"], "forged")
        self.assertTrue(audit.audit_check()["valid"])

    def test_check_reports_malformed_line_without_hiding_valid_records(self) -> None:
        audit.log_event("valid.event")
        path = self.root / audit.AUDIT_LOG
        with path.open("a", encoding="utf-8") as handle:
            handle.write("not-json\n")
        report = audit.inspect_audit_log()
        self.assertFalse(report["valid"])
        self.assertEqual(report["record_count"], 1)
        self.assertIn("line 2: invalid JSON", report["issues"][0])

    def test_export_contains_records_and_cannot_escape_reports_directory(self) -> None:
        audit.log_event("qualification.completed", status="qualified")
        path = audit.export_audit("qualification-audit.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.parent, self.root / "workspace" / "reports")
        self.assertEqual(payload["format"], "haness-frame-audit-export")
        self.assertEqual(payload["record_count"], 1)
        with self.assertRaisesRegex(ValueError, "plain file name"):
            audit.export_audit("../outside.json")

    def test_recent_events_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 10000"):
            audit.recent_events(0)


if __name__ == "__main__":
    unittest.main()
