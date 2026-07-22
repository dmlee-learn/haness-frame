from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, storage, workflow


class WorkflowValidationTests(unittest.TestCase):
    @contextmanager
    def runtime_patches(self, root: Path):
        with ExitStack() as stack:
            for patcher in (
                patch.object(storage, "ROOT", root),
                patch.object(storage, "WORKSPACE", root / "workspace"),
                patch.object(storage, "STATE_FILE", root / "workspace" / "state.json"),
                patch.object(audit, "ROOT", root),
                patch.object(workflow, "enforce_decision_gate"),
            ):
                stack.enter_context(patcher)
            yield

    def test_empty_sequence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            workflow.normalize_roles(["", " "])

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            workflow.normalize_roles(["planner", "inventor"])

    def test_duplicate_role_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            workflow.normalize_roles(["planner", "planner"])

    def test_backward_sequence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "moves backward"):
            workflow.validate_role_sequence(["reviewer", "planner"])

    def test_forward_sequence_is_allowed(self) -> None:
        workflow.validate_role_sequence(["researcher", "planner", "architect", "reviewer"])

    def test_sequence_persists_invocation_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            diagnostics = {"used_fallback": True, "attempts": [{"route": "primary", "outcome": "failed"}]}
            result = {
                "content": "A sufficiently detailed plan.",
                "provider_type": "openai_compatible",
                "service": {"name": "fallback"},
                "diagnostics": diagnostics,
            }
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                outputs = workflow.run_sequence(["planner"], "make a plan")
            saved = json.loads((root / "workspace" / "executions" / "01-planner.json").read_text(encoding="utf-8"))
            self.assertEqual(outputs[0]["diagnostics"], diagnostics)
            self.assertEqual(saved["diagnostics"], diagnostics)
            self.assertEqual(saved["run_id"], outputs[0]["run_id"])

    def test_latest_recovers_session_when_pointer_update_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def fail_latest(path: str, content: str) -> Path:
                if path == workflow.LATEST_SESSION:
                    raise OSError("injected latest pointer failure")
                return storage.write_text(path, content)

            with self.runtime_patches(root), patch.object(workflow, "write_text", side_effect=fail_latest):
                with self.assertRaisesRegex(OSError, "latest pointer failure"):
                    workflow.run_sequence(["planner"], "recover the durable session")
            with self.runtime_patches(root):
                recovered = workflow.load_pipeline_session("latest")
                self.assertEqual(recovered["status"], "pending")
                self.assertEqual(recovered["roles"], ["planner"])

            result = {"content": "A sufficiently detailed recovered plan.", "provider_type": "fixture"}
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                outputs = workflow.resume_sequence(str(recovered["run_id"]))
                self.assertEqual(len(outputs), 1)
                self.assertEqual(workflow.load_pipeline_session("latest")["status"], "completed")

    def test_resume_uses_cached_success_after_pre_checkpoint_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = {"content": "A sufficiently detailed durable plan.", "provider_type": "fixture"}
            original_write = storage.write_text

            def crash_before_role_checkpoint(path: str, content: str) -> Path:
                if path.startswith(workflow.RUN_ROOT) and path.endswith("/01-planner.json"):
                    raise KeyboardInterrupt("injected crash after provider success")
                return original_write(path, content)

            with (
                self.runtime_patches(root),
                patch.object(workflow, "invoke", return_value=result) as initial_invoke,
                patch.object(workflow, "write_text", side_effect=crash_before_role_checkpoint),
            ):
                with self.assertRaisesRegex(KeyboardInterrupt, "after provider success"):
                    workflow.run_sequence(["planner"], "cache the successful role")
                interrupted = workflow.load_pipeline_session("latest")
                self.assertEqual(interrupted["role_call_inflight"], 1)
                self.assertEqual(interrupted["budget"]["ai_calls"], 1)
                initial_invoke.assert_called_once()

            with self.runtime_patches(root), patch.object(workflow, "invoke") as repeated_provider:
                outputs = workflow.resume_sequence(str(interrupted["run_id"]))
                repeated_provider.assert_not_called()
                self.assertEqual(outputs[0]["content"], "A sufficiently detailed durable plan.")
                self.assertTrue(outputs[0]["cache_hit"])
                completed = workflow.load_pipeline_session(str(interrupted["run_id"]))
                self.assertEqual(completed["budget"]["ai_calls"], 1)
                self.assertEqual(completed["role_call_inflight"], 0)

    def test_failed_sequence_resumes_without_repeating_completed_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = {"content": "A sufficiently detailed plan.", "provider_type": "fixture", "service": {"name": "one"}}
            second = {"content": "A sufficiently detailed critique.", "provider_type": "fixture", "service": {"name": "two"}}
            with (
                self.runtime_patches(root),
                patch.object(workflow, "invoke", side_effect=[first, RuntimeError("temporary failure")]) as initial_invoke,
            ):
                with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                    workflow.run_sequence(["planner", "critic"], "review this plan")
                failed = workflow.load_pipeline_session("latest")
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(len(failed["results"]), 1)
                self.assertEqual(initial_invoke.call_count, 2)

                with patch.object(workflow, "invoke", return_value=second) as resumed_invoke:
                    results = workflow.resume_sequence(str(failed["run_id"]))
                self.assertEqual(resumed_invoke.call_count, 1)
                self.assertEqual([item["role"] for item in results], ["planner", "critic"])
                self.assertIn("Previous role (planner) output:\nA sufficiently detailed plan.", resumed_invoke.call_args.kwargs["system"])
                self.assertEqual(workflow.load_pipeline_session(str(failed["run_id"]))["status"], "completed")

    def test_completed_sequence_resume_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = {"content": "A completed pipeline result.", "provider_type": "fixture", "service": {}}
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                outputs = workflow.run_sequence(["planner"], "finish once")
                with patch.object(workflow, "invoke") as invoke_again:
                    resumed = workflow.resume_sequence(str(outputs[0]["run_id"]))
            invoke_again.assert_not_called()
            self.assertEqual(resumed, outputs)

    def test_pipeline_run_id_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            workflow.load_pipeline_session("../outside")

    def test_pipeline_resume_rejects_corrupted_saved_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = {"content": "A trusted pipeline output.", "provider_type": "fixture", "service": {}}
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                outputs = workflow.run_sequence(["planner"], "preserve output integrity")
                run_id = str(outputs[0]["run_id"])
                session_path = root / "workspace" / "executions" / "runs" / run_id / "session.json"
                session = json.loads(session_path.read_text(encoding="utf-8"))
                session["results"][0]["content"] = "corrupted"
                session_path.write_text(json.dumps(session), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                    workflow.resume_sequence(run_id)

    def test_pipeline_loader_rejects_tampered_result_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = {
                "content": "A trusted pipeline output.",
                "provider_type": "fixture",
                "service": {"model": "original-model"},
            }
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                outputs = workflow.run_sequence(["planner"], "preserve provenance")
                run_id = str(outputs[0]["run_id"])
                session_path = root / "workspace" / "executions" / "runs" / run_id / "session.json"
                session = json.loads(session_path.read_text(encoding="utf-8"))
                session["results"][0]["service"]["model"] = "tampered-model"
                session_path.write_text(json.dumps(session), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "provenance hash mismatch"):
                    workflow.load_pipeline_session(run_id)

    def test_ai_call_budget_is_terminal_and_survives_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            limits = {
                "max_roles": 16,
                "max_prompt_chars": 20000,
                "max_system_chars": 40000,
                "max_context_chars": 60000,
                "max_elapsed_seconds": 1800,
                "max_ai_calls": 1,
            }
            result = {"content": "A valid first role output.", "provider_type": "fixture", "service": {}}
            with (
                self.runtime_patches(root),
                patch.object(workflow, "load_orchestration_policy", return_value=limits),
                patch.object(workflow, "invoke", return_value=result) as invoke_role,
            ):
                with self.assertRaisesRegex(workflow.BudgetExceeded, "AI-call budget"):
                    workflow.run_sequence(["planner", "critic"], "bounded pipeline")
                session = workflow.load_pipeline_session("latest")
                self.assertEqual(session["status"], "budget_exhausted")
                self.assertEqual(session["budget"]["ai_calls"], 1)
                self.assertEqual(invoke_role.call_count, 1)
                with self.assertRaisesRegex(RuntimeError, "terminal"):
                    workflow.resume_sequence(str(session["run_id"]))

    def test_context_policy_keeps_invocation_within_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            limits = {
                "max_roles": 16,
                "max_prompt_chars": 20000,
                "max_system_chars": 40000,
                "max_context_chars": 1000,
                "max_elapsed_seconds": 1800,
                "max_ai_calls": 16,
            }
            responses = [
                {"content": "x" * 3000, "provider_type": "fixture", "service": {}},
                {"content": "A sufficiently detailed review.", "provider_type": "fixture", "service": {}},
            ]
            with (
                self.runtime_patches(root),
                patch.object(workflow, "load_orchestration_policy", return_value=limits),
                patch.object(workflow, "invoke", side_effect=responses),
            ):
                outputs = workflow.run_sequence(["planner", "critic"], "bounded context")
            self.assertLessEqual(len(str(outputs[1]["system"])), 1000)
            self.assertTrue(outputs[1]["context_truncated"])
            self.assertEqual(outputs[1]["context_omitted_roles"], 1)

    def test_short_role_output_is_checkpointed_as_failure_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                self.runtime_patches(root),
                patch.object(workflow, "invoke", return_value={"content": "short", "provider_type": "fixture"}),
            ):
                with self.assertRaisesRegex(ValueError, "shorter than"):
                    workflow.run_sequence(["planner"], "require useful output")
                failed = workflow.load_pipeline_session("latest")
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["results"], [])
                self.assertEqual(failed["budget"]["ai_calls"], 1)
                valid = {"content": "A sufficiently detailed planning result.", "provider_type": "fixture"}
                with patch.object(workflow, "invoke", return_value=valid):
                    resumed = workflow.resume_sequence(str(failed["run_id"]))
                final_session = workflow.load_pipeline_session(str(failed["run_id"]))
            self.assertEqual(len(resumed), 1)
            self.assertEqual(resumed[0]["content"], valid["content"])
            self.assertEqual(final_session["budget"]["ai_calls"], 2)

    def test_failed_pipeline_can_be_explicitly_abandoned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                self.runtime_patches(root),
                patch.object(workflow, "invoke", return_value={"content": "short", "provider_type": "fixture"}),
            ):
                with self.assertRaises(ValueError):
                    workflow.run_sequence(["planner"], "obsolete run")
                failed = workflow.load_pipeline_session("latest")
                abandoned = workflow.abandon_sequence(str(failed["run_id"]), "Superseded by a corrected task")
                self.assertEqual(abandoned["status"], "abandoned")
                self.assertEqual(abandoned["abandonment_reason"], "Superseded by a corrected task")
                self.assertEqual(workflow.abandon_sequence(str(failed["run_id"]), "ignored"), abandoned)
                with self.assertRaisesRegex(RuntimeError, "abandoned"):
                    workflow.resume_sequence(str(failed["run_id"]))

    def test_pipeline_audit_does_not_store_prompt_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prompt = "Sensitive pipeline task details"
            result = {"content": "A sufficiently detailed role output.", "provider_type": "fixture"}
            with self.runtime_patches(root), patch.object(workflow, "invoke", return_value=result):
                workflow.run_sequence(["planner"], prompt)
            audit_text = (root / "workspace" / "logs" / "audit.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(prompt, audit_text)
            self.assertIn("prompt_sha256", audit_text)


if __name__ == "__main__":
    unittest.main()
