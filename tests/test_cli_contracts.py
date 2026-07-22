from __future__ import annotations

import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import cli


class CliExitContractTests(unittest.TestCase):
    def call(self, function, *args) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return function(*args)

    def test_gate_returns_nonzero_when_closed(self) -> None:
        report = {"allowed": False, "issues": ["closed"]}
        with (
            patch.object(cli, "decision_gate", return_value=report),
            patch.object(cli, "refresh_runtime_scorecard"),
        ):
            self.assertEqual(self.call(cli.print_gate), 1)

    def test_live_check_parser_uses_bounded_defaults(self) -> None:
        args = cli.build_parser().parse_args(["live-check"])
        with patch.object(cli, "print_live_check", return_value=0) as check:
            self.assertEqual(args.func(args), 0)
        check.assert_called_once_with(role="planner", timeout=2.0, max_tokens=32, retries=0)

    def test_claim_check_returns_nonzero_when_invalid(self) -> None:
        with patch.object(cli, "claim_policy_report", return_value={"valid": False, "issues": ["invalid"]}):
            self.assertEqual(self.call(cli.print_claim_check), 1)

    def test_archive_verify_returns_nonzero_when_invalid(self) -> None:
        args = argparse.Namespace(file="broken.zip")
        with patch.object(cli, "verify_archive", return_value={"valid": False, "issues": ["invalid"]}):
            self.assertEqual(self.call(cli.print_archive_verify, args), 1)

    def test_verification_plan_returns_nonzero_when_rejected(self) -> None:
        with patch.object(cli, "verification_plan", return_value={"approved": False, "commands": []}):
            self.assertEqual(self.call(cli.print_verification_plan), 1)

    def test_verification_run_returns_nonzero_when_tests_fail(self) -> None:
        args = argparse.Namespace(continue_on_failure=False)
        with patch.object(cli, "run_verification_commands", return_value={"passed": False, "results": []}):
            self.assertEqual(self.call(cli.print_verification_run, args), 1)

    def test_verify_requires_compile_manifest_and_gate(self) -> None:
        report = {
            "compileall": True,
            "manifest": {"valid": True},
            "gate": {"allowed": False},
        }
        with patch.object(cli, "run_verify", return_value=report):
            self.assertEqual(self.call(cli.print_verify), 1)
        report["gate"]["allowed"] = True
        with patch.object(cli, "run_verify", return_value=report):
            self.assertEqual(self.call(cli.print_verify), 0)

    def test_finish_returns_two_until_completed(self) -> None:
        args = argparse.Namespace(label="")
        with patch.object(cli, "finish_project", return_value={"status": "blocked"}):
            self.assertEqual(self.call(cli.print_finish, args), 2)
        with patch.object(cli, "finish_project", return_value={"status": "completed"}):
            self.assertEqual(self.call(cli.print_finish, args), 0)

    def test_implementation_returns_two_until_completed(self) -> None:
        args = argparse.Namespace(task="Build", max_tokens=None, retries=0, label="implementation")
        with patch.object(cli, "implement_project", return_value={"status": "rolled_back"}):
            self.assertEqual(self.call(cli.print_implementation, args), 2)
        with patch.object(cli, "implement_project", return_value={"status": "completed"}):
            self.assertEqual(self.call(cli.print_implementation, args), 0)

    def test_repair_result_uses_two_for_durable_unsuccessful_status(self) -> None:
        self.assertEqual(self.call(cli.print_repair_result, {"status": "approved"}), 0)
        self.assertEqual(self.call(cli.print_repair_result, {"status": "already_verified"}), 0)
        self.assertEqual(self.call(cli.print_repair_result, {"status": "attempts_exhausted"}), 2)
        self.assertEqual(self.call(cli.print_repair_result, {"status": "budget_exhausted"}), 2)

    def test_orchestration_reconcile_uses_wrapper_status_contract(self) -> None:
        self.assertEqual(self.call(cli.print_orchestration_run, {"status": "completed"}), 0)
        self.assertEqual(self.call(cli.print_orchestration_run, {"status": "failed"}), 2)

    def test_reconcile_all_returns_nonzero_for_internal_failures(self) -> None:
        args = argparse.Namespace(limit=10)
        with patch.object(
            cli,
            "reconcile_orchestration_executions",
            return_value={"failures": [{"execution_id": "one", "error_type": "ValueError"}]},
        ):
            self.assertEqual(self.call(cli.print_orchestration_reconcile_all, args), 1)


if __name__ == "__main__":
    unittest.main()
