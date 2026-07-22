from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import budget


class RunBudgetTests(unittest.TestCase):
    def test_elapsed_time_boundary_is_terminal(self) -> None:
        with patch.object(budget.time, "monotonic", side_effect=[100.0, 109.9, 110.0]):
            run_budget = budget.RunBudget(max_elapsed_seconds=10, max_ai_calls=3)
            run_budget.check("before boundary")
            with self.assertRaisesRegex(budget.BudgetExceeded, "elapsed-time"):
                run_budget.check("at boundary")

    def test_ai_call_limit_rejects_next_role(self) -> None:
        with patch.object(budget.time, "monotonic", return_value=100.0):
            run_budget = budget.RunBudget(max_elapsed_seconds=10, max_ai_calls=1)
            run_budget.reserve_ai_call("debugger")
            with self.assertRaisesRegex(budget.BudgetExceeded, "coder"):
                run_budget.reserve_ai_call("coder")
            self.assertEqual(run_budget.snapshot()["ai_calls"], 1)

    def test_restored_usage_counts_toward_limits(self) -> None:
        with patch.object(budget.time, "monotonic", return_value=100.0):
            run_budget = budget.RunBudget(
                max_elapsed_seconds=60,
                max_ai_calls=2,
                initial_elapsed_seconds=4.5,
                initial_ai_calls=2,
            )
            self.assertEqual(run_budget.snapshot()["elapsed_seconds"], 4.5)
            with self.assertRaisesRegex(budget.BudgetExceeded, "reviewer"):
                run_budget.reserve_ai_call("reviewer")


if __name__ == "__main__":
    unittest.main()
