from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import cli


class OrchestrationCliTests(unittest.TestCase):
    def test_run_exit_code_reflects_wrapper_status(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.print_orchestration_run({"status": "completed"}), 0)
            self.assertEqual(cli.print_orchestration_run({"status": "failed"}), 2)
            self.assertEqual(
                cli.print_orchestration_run({"execution": {"status": "failed"}, "result": {}}), 2
            )

    def test_main_audits_nonzero_function_result_as_failure(self) -> None:
        args = SimpleNamespace(command="orchestrate", func=lambda parsed: 2)
        parser = Mock()
        parser.parse_args.return_value = args
        with (
            patch.object(cli, "build_parser", return_value=parser),
            patch.object(cli, "log_event") as log,
        ):
            self.assertEqual(cli.main(), 2)
        log.assert_any_call("cli.command.failed", command="orchestrate", exit_code=2)
        self.assertNotIn(
            (("cli.command.completed",), {"command": "orchestrate"}),
            [(call.args, call.kwargs) for call in log.call_args_list],
        )


if __name__ == "__main__":
    unittest.main()
