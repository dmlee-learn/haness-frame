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

from haness_frame_app.templates.runtime import audit, orchestration_recovery, storage


class OrchestrationRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.patchers = [patch.object(storage, "ROOT", self.root), patch.object(audit, "ROOT", self.root)]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_execution(self, execution_id: str, child_id: str, *, status: str = "running") -> None:
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "execution_id": execution_id,
                    "status": status,
                    "linked_session": {"kind": "pipeline", "id": child_id, "status": "running"},
                }
            ),
            encoding="utf-8",
        )

    def test_only_terminal_existing_children_are_reconciled(self) -> None:
        terminal_id = "orchestration-20260720T100000000000Z"
        active_id = "orchestration-20260720T100000000001Z"
        missing_id = "orchestration-20260720T100000000002Z"
        self.write_execution(terminal_id, "terminal-child")
        self.write_execution(active_id, "active-child")
        self.write_execution(missing_id, "missing-child")
        for child_id in ("terminal-child", "active-child"):
            path = self.root / "workspace" / "executions" / "runs" / child_id / "session.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

        def child_state(kind: str, child_id: str) -> dict[str, str]:
            return {"status": "completed" if child_id == "terminal-child" else "running"}

        with (
            patch.object(orchestration_recovery, "_load_child_session", side_effect=child_state),
            patch.object(
                orchestration_recovery,
                "reconcile_orchestration_execution",
                return_value={"status": "completed"},
            ) as reconcile,
        ):
            report = orchestration_recovery.reconcile_orchestration_executions()
        reconcile.assert_called_once_with(terminal_id)
        self.assertEqual(report["scanned"], 3)
        self.assertEqual(report["skipped"], {"resolved": 0, "active": 1, "missing_child": 1})
        self.assertEqual(report["reconciled"], [{"execution_id": terminal_id, "status": "completed"}])
        self.assertEqual(report["failures"], [])

    def test_limit_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 200"):
            orchestration_recovery.reconcile_orchestration_executions(limit=0)
        with self.assertRaisesRegex(ValueError, "between 1 and 200"):
            orchestration_recovery.reconcile_orchestration_executions(limit=201)


if __name__ == "__main__":
    unittest.main()
