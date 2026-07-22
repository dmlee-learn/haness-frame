from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, evidence, scorecard, storage


class AtomicStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(evidence, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_replace_failure_preserves_existing_file_and_removes_temp(self) -> None:
        target = self.root / "workspace" / "state.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"state":"original"}', encoding="utf-8")
        with patch.object(storage.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected replace failure"):
                storage.write_path_text(target, '{"state":"new"}')
        self.assertEqual(target.read_text(encoding="utf-8"), '{"state":"original"}')
        self.assertEqual(list(target.parent.glob(".state.json.*.tmp")), [])

    def test_malformed_json_update_fails_without_overwriting_original(self) -> None:
        target = self.root / "workspace" / "state.json"
        target.parent.mkdir(parents=True)
        original = '{"status":"important",}'
        target.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contains invalid JSON at line"):
            storage.update_json_path(target, lambda state: state.update({"status": "replaced"}))
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_non_object_json_update_fails_without_overwriting_original(self) -> None:
        target = self.root / "workspace" / "scorecard.json"
        target.parent.mkdir(parents=True)
        target.write_text('["preserve-me"]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "root must be a JSON object"):
            storage.update_json_path(target, lambda value: value.update({"changed": True}))
        self.assertEqual(target.read_text(encoding="utf-8"), '["preserve-me"]')

    def test_load_state_reports_corruption_without_content_echo(self) -> None:
        target = self.root / "workspace" / "state.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"secret-value":', encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            storage.load_state()
        self.assertIn("invalid JSON at line", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_scorecard_mutation_preserves_corrupt_file(self) -> None:
        target = self.root / "workspace" / "scorecard.json"
        target.parent.mkdir(parents=True)
        original = "{broken-scorecard"
        target.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contains invalid JSON"):
            scorecard.mark_check("test", True)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_scorecard_load_reports_corruption_without_content_echo(self) -> None:
        target = self.root / "workspace" / "scorecard.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"secret-score":', encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            scorecard.load_scorecard()
        self.assertIn("invalid JSON at line", str(raised.exception))
        self.assertNotIn("secret-score", str(raised.exception))

    def test_concurrent_writes_never_leave_a_partial_payload(self) -> None:
        target = self.root / "workspace" / "concurrent.json"
        payloads = [json.dumps({"writer": index, "data": str(index) * 5000}) for index in range(12)]
        threads = [threading.Thread(target=storage.write_path_text, args=(target, payload)) for payload in payloads]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        final_payload = target.read_text(encoding="utf-8")
        self.assertIn(final_payload, payloads)
        self.assertIsInstance(json.loads(final_payload), dict)

    def test_concurrent_audit_appends_preserve_every_record(self) -> None:
        threads = [threading.Thread(target=audit.log_event, args=("storage.concurrent",), kwargs={"index": index}) for index in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        report = audit.inspect_audit_log()
        self.assertTrue(report["valid"], report["issues"])
        self.assertEqual(report["record_count"], 20)
        self.assertEqual(report["event_counts"], {"storage.concurrent": 20})

    def test_separate_processes_preserve_every_audit_record(self) -> None:
        script = (
            "import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd()/'src')); "
            "from haness_frame_app.templates.runtime import audit, storage; "
            "root=Path(sys.argv[1]); storage.ROOT=root; storage.WORKSPACE=root/'workspace'; "
            "storage.STATE_FILE=storage.WORKSPACE/'state.json'; audit.ROOT=root; "
            "audit.log_event('storage.process', index=int(sys.argv[2]))"
        )
        processes = [
            subprocess.Popen([sys.executable, "-c", script, str(self.root), str(index)])
            for index in range(8)
        ]
        for process in processes:
            self.assertEqual(process.wait(timeout=10), 0)
        report = audit.inspect_audit_log()
        self.assertTrue(report["valid"], report["issues"])
        self.assertEqual(report["record_count"], 8)
        self.assertEqual(report["event_counts"], {"storage.process": 8})

    def test_concurrent_scorecard_updates_do_not_lose_checks(self) -> None:
        threads = [
            threading.Thread(target=scorecard.mark_check, args=(f"check_{index}", True, f"detail {index}"))
            for index in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        report = scorecard.load_scorecard()
        self.assertEqual(len(report["checks"]), 20)
        self.assertEqual(len(report["details"]), 20)

    def test_active_operation_lock_rejects_duplicate_session_work(self) -> None:
        with storage.operation_lock("pipeline", "run-one"):
            with self.assertRaisesRegex(RuntimeError, "already active"):
                with storage.operation_lock("pipeline", "run-one", timeout=0.05):
                    self.fail("duplicate lock must not be acquired")

    def test_dead_operation_owner_lock_is_recovered(self) -> None:
        target = self.root / "workspace" / ".operations" / "debate-dead-owner"
        lock_path = storage._lock_path(target)
        lock_path.write_text("pid=2147483647 created=0\n", encoding="ascii")
        with storage.operation_lock("debate", "dead-owner", timeout=0.2):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())

    def test_concurrent_evidence_additions_do_not_lose_records(self) -> None:
        errors: list[Exception] = []

        def add(index: int) -> None:
            try:
                evidence.add_evidence(
                    query=f"query {index}",
                    provider="fixture",
                    url=f"https://example.com/source-{index}",
                    title=f"Source {index}",
                    excerpt="A substantive evidence excerpt for concurrent storage testing.",
                    confidence="high",
                    why_it_matters="It verifies that concurrent records are preserved.",
                    recommended_use="Use this source in the storage decision.",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add, args=(index,)) for index in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        records = evidence.load_evidence()
        self.assertEqual(len(records), 10)
        self.assertEqual(len({record["url"] for record in records}), 10)

    def test_latest_session_prefers_newer_durable_original(self) -> None:
        root = self.root / "workspace" / "executions" / "runs"
        older = {
            "run_id": "older",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        newer = {
            "run_id": "newer",
            "updated_at": "2026-01-01T00:01:00+00:00",
        }
        (root / "older").mkdir(parents=True)
        (root / "newer").mkdir(parents=True)
        (root / "older" / "session.json").write_text(json.dumps(older), encoding="utf-8")
        (root / "newer" / "session.json").write_text(json.dumps(newer), encoding="utf-8")
        latest = self.root / "workspace" / "executions" / "latest-session.json"
        latest.write_text(json.dumps(older), encoding="utf-8")
        selected = storage.read_latest_session(
            "workspace/executions/latest-session.json",
            "workspace/executions/runs",
        )
        self.assertEqual(json.loads(selected)["run_id"], "newer")


if __name__ == "__main__":
    unittest.main()
