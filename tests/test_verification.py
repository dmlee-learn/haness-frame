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

from haness_frame_app.templates.runtime import audit, storage, verification


class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "docs").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(verification, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_decision(self, command: str) -> None:
        (self.root / "docs" / "03-decision-record.md").write_text(
            f"# Decision\n\n## Verification Commands\n\n- `{command}`\n\n## Rollback Plan\n",
            encoding="utf-8",
        )

    def write_policy(self, commands: list[str]) -> None:
        payload = {
            "allowed_commands": commands,
            "timeout_seconds": 30,
            "max_output_chars": 4000,
        }
        (self.root / "workspace" / "verification-policy.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_plan_requires_exact_policy_match(self) -> None:
        self.write_decision("python -m compileall src")
        self.write_policy(["python app.py verify"])

        plan = verification.verification_plan()

        self.assertFalse(plan["approved"])
        self.assertEqual(plan["commands"][0]["reason"], "command is not in workspace/verification-policy.json")

    def test_policy_identity_preserves_whitespace_inside_quoted_argument(self) -> None:
        self.write_decision('python -c "print(\'a b\')"')
        self.write_policy(['python -c "print(\'a  b\')"'])
        plan = verification.verification_plan()
        self.assertFalse(plan["approved"])
        self.assertEqual(plan["commands"][0]["reason"], "command is not in workspace/verification-policy.json")

    def test_plan_rejects_shell_operators_even_when_listed(self) -> None:
        command = "python app.py verify & echo unsafe"
        self.write_decision(command)
        self.write_policy([command])

        plan = verification.verification_plan()

        self.assertFalse(plan["approved"])
        self.assertEqual(plan["commands"][0]["reason"], "shell operators are not allowed")

    def test_plan_rejects_command_substitution_and_control_characters(self) -> None:
        for command in ("python -c $(unsafe)", "python -m unittest\nsecond-command"):
            with self.subTest(command=command):
                self.write_decision(command)
                self.write_policy([command])
                plan = verification.verification_plan()
                self.assertFalse(plan["approved"])
                self.assertEqual(plan["commands"][0]["reason"], "shell operators are not allowed")

    def test_posix_argument_parsing_and_bare_python_resolution(self) -> None:
        with patch.object(verification.os, "name", "posix"):
            args = verification._command_args("python3 -c 'print(1 + 2)'")
        self.assertEqual(args, [sys.executable, "-c", "print(1 + 2)"])

    def test_windows_argument_parsing_and_py_selector_resolution(self) -> None:
        with patch.object(verification.os, "name", "nt"):
            args = verification._command_args('py -3.12 "tests\\test file.py"')
        self.assertEqual(args, [sys.executable, "tests\\test file.py"])

    def test_explicit_python_path_is_preserved(self) -> None:
        command = "/opt/project/.venv/bin/python -m unittest"
        with patch.object(verification.os, "name", "posix"):
            args = verification._command_args(command)
        self.assertEqual(args[0], "/opt/project/.venv/bin/python")

    def test_run_executes_approved_command_and_writes_report(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "src" / "sample.py").write_text("value = 1\n", encoding="utf-8")
        command = "python -m compileall src"
        self.write_decision(command)
        self.write_policy([command])

        with patch.object(verification, "enforce_decision_gate"):
            report = verification.run_verification_commands()

        self.assertTrue(report["passed"])
        self.assertEqual(report["executed_commands"], 1)
        self.assertTrue((self.root / "workspace" / "verifications" / "latest.json").exists())

    def test_run_executes_quoted_script_path_with_spaces(self) -> None:
        script = self.root / "tools with space" / "check.py"
        script.parent.mkdir()
        script.write_text("print('cross-platform path ok')\n", encoding="utf-8")
        command = 'python "tools with space/check.py"'
        self.write_decision(command)
        self.write_policy([command])
        with patch.object(verification, "enforce_decision_gate"):
            report = verification.run_verification_commands()
        self.assertTrue(report["passed"])
        self.assertIn("cross-platform path ok", report["results"][0]["stdout"])

    def test_run_records_missing_executable_as_failure(self) -> None:
        command = "missing-harness-test-tool --version"
        self.write_decision(command)
        self.write_policy([command])

        with patch.object(verification, "enforce_decision_gate"):
            report = verification.run_verification_commands()

        self.assertFalse(report["passed"])
        self.assertIsNone(report["results"][0]["returncode"])
        self.assertTrue(report["results"][0]["stderr"])

    def test_invalid_policy_limit_has_clear_error(self) -> None:
        command = "python -m compileall src"
        self.write_decision(command)
        self.write_policy([command])
        policy_path = self.root / "workspace" / "verification-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["timeout_seconds"] = None
        policy_path.write_text(json.dumps(policy), encoding="utf-8")

        with patch.object(verification, "enforce_decision_gate"):
            with self.assertRaisesRegex(ValueError, "timeout_seconds must be an integer"):
                verification.run_verification_commands()


if __name__ == "__main__":
    unittest.main()
