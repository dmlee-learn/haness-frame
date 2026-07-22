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

from haness_frame_app.templates.runtime import orchestration_policy, storage


class OrchestrationPolicyTests(unittest.TestCase):
    def test_defaults_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(storage, "ROOT", Path(temp_dir)):
            policy = orchestration_policy.load_orchestration_policy()
        self.assertGreaterEqual(policy["max_ai_calls"], policy["max_roles"])
        self.assertGreater(policy["max_context_chars"], policy["max_prompt_chars"])
        self.assertGreaterEqual(policy["max_debate_ai_calls"], policy["max_roles"])
        self.assertGreaterEqual(policy["max_debate_elapsed_seconds"], policy["max_elapsed_seconds"])

    def test_invalid_integer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "workspace").mkdir()
            (root / orchestration_policy.POLICY_FILE).write_text(
                json.dumps({"max_ai_calls": "unlimited"}), encoding="utf-8"
            )
            with patch.object(storage, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "must be an integer"):
                    orchestration_policy.load_orchestration_policy()

    def test_out_of_range_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "workspace").mkdir()
            (root / orchestration_policy.POLICY_FILE).write_text(
                json.dumps({"max_elapsed_seconds": 0}), encoding="utf-8"
            )
            with patch.object(storage, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "between"):
                    orchestration_policy.load_orchestration_policy()

    def test_output_minimum_cannot_exceed_maximum(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "workspace").mkdir()
            (root / orchestration_policy.POLICY_FILE).write_text(
                json.dumps({"min_output_chars": 500, "max_output_chars": 100}), encoding="utf-8"
            )
            with patch.object(storage, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "must not exceed"):
                    orchestration_policy.load_orchestration_policy()

    def test_independent_judge_requirement_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "workspace").mkdir()
            (root / orchestration_policy.POLICY_FILE).write_text(
                json.dumps({"require_independent_debate_judge_service": "yes"}), encoding="utf-8"
            )
            with patch.object(storage, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "must be a boolean"):
                    orchestration_policy.load_orchestration_policy()


if __name__ == "__main__":
    unittest.main()
