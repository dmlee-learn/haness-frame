from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, orchestration, storage


class OrchestrationTests(unittest.TestCase):
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

    @staticmethod
    def services() -> dict[str, object]:
        return {
            "role_services": {
                role: {
                    "name": f"local-{role}",
                    "provider_type": "ollama",
                    "model": "local-model",
                    "enabled": True,
                }
                for role in orchestration.ROLE_ORDER
            }
        }

    @staticmethod
    def pipeline_outputs(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [{"run_id": kwargs["run_id"], "role": "planner", "content": "plan"}]

    @staticmethod
    def repair_result(status: str):
        def result(*args: object, **kwargs: object) -> dict[str, object]:
            return {"session_id": kwargs["session_id"], "status": status}

        return result

    def mutate_plan_and_rebind_wrapper(
        self, execution_id: str, mutate: Callable[[dict[str, object]], None]
    ) -> None:
        execution_path = (
            self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        )
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        plan_path = self.root / "workspace" / "orchestration" / f"{execution['plan_id']}.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        mutate(plan)
        plan["plan_sha256"] = orchestration.orchestration_plan_sha256(plan)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        execution["plan_sha256"] = plan["plan_sha256"]
        execution["execution_sha256"] = orchestration.orchestration_execution_sha256(execution)
        execution_path.write_text(json.dumps(execution), encoding="utf-8")

    def test_bugfix_plan_orders_debugger_before_gated_implementation(self) -> None:
        gate = {"allowed": False, "issues": ["evidence required"]}
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value=gate),
        ):
            plan = orchestration.build_role_plan("오류를 수정하고 테스트를 추가해 주세요")
        self.assertIn("bugfix", plan["task_tags"])
        self.assertLess(plan["recommended_roles"].index("debugger"), plan["recommended_roles"].index("coder"))
        self.assertEqual([item["role"] for item in plan["blocked_roles"]], ["coder", "reviewer"])
        self.assertTrue((self.root / "workspace" / "orchestration" / "latest.json").is_file())

    def test_research_ui_architecture_plan_is_forward_ordered(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            plan = orchestration.build_role_plan("Research and design a security API frontend architecture")
        self.assertEqual(plan["task_tags"], ["research", "ui", "architecture", "high_risk"])
        positions = [orchestration.ROLE_ORDER.index(role) for role in plan["recommended_roles"]]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("escalation", plan["recommended_roles"])

    def test_missing_service_is_reported_without_removing_role(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value={"role_services": {}}),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            plan = orchestration.build_role_plan("Implement a small feature")
        self.assertIn("coder", plan["recommended_roles"])
        self.assertTrue(all("service is not assigned" in item["blockers"] for item in plan["blocked_roles"]))

    def test_empty_and_oversized_tasks_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            orchestration.classify_task("  ")
        with self.assertRaisesRegex(ValueError, "10000"):
            orchestration.classify_task("x" * 10001)

    def test_execution_options_are_validated_before_plan_creation(self) -> None:
        invalid = [
            {"rounds": 0},
            {"rounds": True},
            {"retries": -1},
            {"retries": 21},
            {"max_attempts": 0},
            {"max_attempts": True},
        ]
        for options in invalid:
            with self.subTest(options=options):
                with (
                    patch.object(orchestration, "build_role_plan") as build,
                    self.assertRaisesRegex(ValueError, "orchestration execution"),
                ):
                    orchestration.execute_task("Plan a migration", **options)
                build.assert_not_called()

    def test_planning_stage_executes_recommended_forward_roles(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": False, "issues": ["closed"]}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs) as run,
        ):
            result = orchestration.execute_task("Research a database migration", stage="planning", retries=2)
        self.assertEqual(result["stage"], "planning")
        self.assertEqual(result["result"][0]["run_id"], run.call_args.kwargs["run_id"])
        roles = run.call_args.args[0]
        self.assertNotIn("coder", roles)
        self.assertEqual([orchestration.ROLE_ORDER.index(role) for role in roles], sorted(
            orchestration.ROLE_ORDER.index(role) for role in roles
        ))
        self.assertEqual(run.call_args.kwargs["retries"], 2)
        self.assertRegex(run.call_args.kwargs["run_id"], r"^pipeline-\d{8}T\d{12}Z-[0-9a-f]{10}$")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        self.assertEqual(execution["linked_session"]["id"], run.call_args.kwargs["run_id"])
        self.assertEqual(execution["linked_session"]["status"], "completed")
        serialized = json.dumps(execution)
        self.assertNotIn("Research a database migration", serialized)
        self.assertNotIn('"content": "plan"', serialized)

    def test_format_v2_execution_rejects_checkpoint_tampering(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["linked_session"]["id"] = "pipeline-tampered"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "provenance hash mismatch"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_rejects_rehashed_child_id_tampering(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["linked_session"]["id"] = "pipeline-tampered"
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "child id does not match its reservation"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_is_bound_to_saved_plan_task(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["task_sha256"] = "0" * 64
        stamp = execution_id.removeprefix("orchestration-")
        payload["linked_session"]["id"] = f"pipeline-{stamp}-0000000000"
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "task hash does not match its plan"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_rejects_saved_plan_tampering(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        plan_path = self.root / "workspace" / "orchestration" / f"{execution['plan_id']}.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["recommended_commands"].append("python unsafe.py")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "plan provenance hash mismatch"):
            orchestration.load_orchestration_execution(result["execution_id"])

    def test_rehashed_plan_tags_must_match_task_classification(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        self.mutate_plan_and_rebind_wrapper(
            result["execution_id"], lambda plan: plan["task_tags"].append("bugfix")
        )

        with self.assertRaisesRegex(ValueError, "task tags do not match"):
            orchestration.load_orchestration_execution(result["execution_id"])

    def test_rehashed_plan_role_invocability_must_match_blockers(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")

        def invalidate(plan: dict[str, object]) -> None:
            plan["roles"][0]["currently_invocable"] = False

        self.mutate_plan_and_rebind_wrapper(result["execution_id"], invalidate)
        with self.assertRaisesRegex(ValueError, "invocability is inconsistent"):
            orchestration.load_orchestration_execution(result["execution_id"])

    def test_rehashed_plan_commands_must_match_task(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        self.mutate_plan_and_rebind_wrapper(
            result["execution_id"],
            lambda plan: plan["recommended_commands"].append("python unsafe.py"),
        )

        with self.assertRaisesRegex(ValueError, "recommended commands do not match"):
            orchestration.load_orchestration_execution(result["execution_id"])

    def test_rehashed_plan_gate_state_must_match_issues(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")

        def invalidate(plan: dict[str, object]) -> None:
            plan["decision_gate"]["allowed"] = False

        self.mutate_plan_and_rebind_wrapper(result["execution_id"], invalidate)
        with self.assertRaisesRegex(ValueError, "decision gate state is inconsistent"):
            orchestration.load_orchestration_execution(result["execution_id"])

    def test_format_v2_execution_roles_must_match_plan_stage(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["roles"] = ["coder"]
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "roles do not match"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_rejects_unknown_child_status(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["linked_session"]["status"] = "invented"
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "child status is invalid"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_rejects_inconsistent_active_status(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["status"] = "running"
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "statuses are inconsistent"):
            orchestration.load_orchestration_execution(execution_id)

    def test_format_v2_execution_rejects_reversed_timestamps(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=self.pipeline_outputs),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution_id = result["execution_id"]
        path = self.root / "workspace" / "orchestration" / "executions" / execution_id / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["updated_at"] = "2000-01-01T00:00:00+00:00"
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "precedes created_at"):
            orchestration.load_orchestration_execution(execution_id)

    def test_debate_stage_uses_recommended_planning_roles(self) -> None:
        verdict = {"status": "completed", "decision": "option-a"}
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_debate_rounds", return_value=verdict) as debate,
        ):
            result = orchestration.execute_task("Compare API architecture options", stage="debate", rounds=3)
        self.assertEqual(result["result"], verdict)
        self.assertEqual(debate.call_args.kwargs["rounds"], 3)
        self.assertEqual(debate.call_args.kwargs["roles"], result["roles"])
        self.assertRegex(debate.call_args.kwargs["session_id"], r"^\d{8}T\d{12}Z$")
        self.assertNotIn("decision_maker", result["roles"])

    def test_debate_rounds_are_checkpointed_after_policy_clamping(self) -> None:
        verdict = {"status": "completed", "decision": "option-a"}
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_debate_rounds", return_value=verdict) as debate,
        ):
            result = orchestration.execute_task(
                "Compare API architecture options", stage="debate", rounds=20
            )
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        self.assertEqual(debate.call_args.kwargs["rounds"], 5)
        self.assertEqual(execution["options"]["rounds"], 5)

    def test_mismatched_child_result_id_is_checkpointed_as_failure(self) -> None:
        outputs = [{"run_id": "pipeline-other", "role": "planner", "content": "plan"}]
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", return_value=outputs),
        ):
            with self.assertRaisesRegex(ValueError, "does not match the reserved child id"):
                orchestration.execute_task("Plan a migration", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        self.assertEqual(execution["status"], "failed")
        self.assertEqual(execution["linked_session"]["status"], "failed")
        self.assertRegex(execution["linked_session"]["id"], r"^pipeline-.*-[0-9a-f]{10}$")

        path = self.root / "workspace" / "orchestration" / "executions" / execution["execution_id"] / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["error"] = ""
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must contain an error"):
            orchestration.load_orchestration_execution(execution["execution_id"])

    def test_repair_stage_enforces_gate_before_execution(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": False, "issues": ["evidence required"]}),
            patch.object(orchestration, "run_repair_loop") as repair,
        ):
            with self.assertRaisesRegex(ValueError, "decision gate is closed"):
                orchestration.execute_task("Fix the failing API", stage="repair")
        repair.assert_not_called()

    def test_repair_stage_runs_bounded_repair_loop(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_repair_loop", side_effect=self.repair_result("approved")) as repair,
        ):
            result = orchestration.execute_task(
                "Fix the failing API and add tests", stage="repair", retries=2, max_attempts=2
            )
        self.assertEqual(result["result"]["status"], "approved")
        self.assertEqual(result["result"]["session_id"], repair.call_args.kwargs["session_id"])
        self.assertEqual(result["roles"], ["debugger", "coder", "reviewer"])
        self.assertEqual(repair.call_args.args, ("Fix the failing API and add tests",))
        self.assertEqual(repair.call_args.kwargs["max_attempts"], 2)
        self.assertEqual(repair.call_args.kwargs["retries"], 2)
        self.assertRegex(repair.call_args.kwargs["session_id"], r"^\d{8}T\d{12}Z$")

    def test_unsuccessful_repair_result_does_not_complete_wrapper(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(
                orchestration,
                "run_repair_loop",
                side_effect=self.repair_result("attempts_exhausted"),
            ),
        ):
            result = orchestration.execute_task("Fix failing tests", stage="repair")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        self.assertEqual(execution["status"], "failed")
        self.assertEqual(execution["linked_session"]["status"], "attempts_exhausted")
        self.assertIn("attempts_exhausted", execution["error"])

    def test_failed_stage_is_checkpointed_without_result_content(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=RuntimeError("provider unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                orchestration.execute_task("Plan a small migration", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        self.assertEqual(execution["status"], "failed")
        self.assertEqual(execution["error"], "provider unavailable")
        self.assertEqual(execution["linked_session"]["status"], "failed")
        self.assertRegex(execution["linked_session"]["id"], r"^pipeline-\d{8}T\d{12}Z-[0-9a-f]{10}$")
        self.assertNotIn("Plan a small migration", json.dumps(execution))

        abandoned = orchestration.abandon_orchestration_execution(
            execution["execution_id"], "replaced after provider recovery"
        )
        self.assertEqual(abandoned["status"], "abandoned")
        audit_text = (self.root / "workspace" / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("replaced after provider recovery", audit_text)

    def test_completed_execution_cannot_be_abandoned(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", return_value=[]),
        ):
            result = orchestration.execute_task("Plan a small migration", stage="planning")
        with self.assertRaisesRegex(ValueError, "completed orchestration"):
            orchestration.abandon_orchestration_execution(result["execution_id"], "not needed")

    def test_abandon_cascades_to_existing_child_session(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=RuntimeError("stage failed")),
        ):
            with self.assertRaises(RuntimeError):
                orchestration.execute_task("Plan child abandonment", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        child_id = str(execution["linked_session"]["id"])
        child_path = self.root / "workspace" / "executions" / "runs" / child_id / "session.json"
        child_path.parent.mkdir(parents=True)
        child_path.write_text("{}", encoding="utf-8")
        with patch.object(
            orchestration,
            "abandon_sequence",
            return_value={"run_id": child_id, "status": "abandoned"},
        ) as abandon:
            result = orchestration.abandon_orchestration_execution(
                execution["execution_id"], "replaced plan"
            )
        abandon.assert_called_once_with(child_id, "replaced plan")
        self.assertEqual(result["status"], "abandoned")
        self.assertEqual(result["linked_session"]["status"], "abandoned")

    def test_abandon_keeps_wrapper_open_when_child_cleanup_fails(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_repair_loop", side_effect=RuntimeError("repair failed")),
        ):
            with self.assertRaises(RuntimeError):
                orchestration.execute_task("Fix tests", stage="repair")
        execution = orchestration.load_orchestration_execution("latest")
        child_id = str(execution["linked_session"]["id"])
        child_path = self.root / "workspace" / "repairs" / child_id / "session.json"
        child_path.parent.mkdir(parents=True)
        child_path.write_text("{}", encoding="utf-8")
        with patch.object(
            orchestration, "abandon_repair_loop", side_effect=RuntimeError("rollback conflict")
        ):
            with self.assertRaisesRegex(RuntimeError, "rollback conflict"):
                orchestration.abandon_orchestration_execution(execution["execution_id"], "stop repair")
        unchanged = orchestration.load_orchestration_execution(execution["execution_id"])
        self.assertEqual(unchanged["status"], "failed")

    def test_hard_interruption_preserves_reserved_child_session_id(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=KeyboardInterrupt("injected crash")),
        ):
            with self.assertRaises(KeyboardInterrupt):
                orchestration.execute_task("Plan crash recovery", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        self.assertEqual(execution["status"], "running")
        self.assertEqual(execution["linked_session"]["status"], "reserved")
        self.assertRegex(execution["linked_session"]["id"], r"^pipeline-\d{8}T\d{12}Z-[0-9a-f]{10}$")

        def finish_reserved(*args: object, **kwargs: object) -> list[dict[str, object]]:
            return [{"run_id": kwargs["run_id"], "role": "planner", "content": "recovered plan"}]

        with patch.object(orchestration, "run_sequence", side_effect=finish_reserved) as run:
            resumed = orchestration.resume_orchestration_execution(execution["execution_id"])
        self.assertEqual(resumed["execution"]["status"], "completed")
        self.assertEqual(run.call_args.kwargs["run_id"], execution["linked_session"]["id"])
        self.assertEqual(
            resumed["execution"]["linked_session"]["id"], execution["linked_session"]["id"]
        )
        idempotent = orchestration.resume_orchestration_execution(execution["execution_id"])
        self.assertIsNone(idempotent["result"])

    def test_resume_uses_existing_child_checkpoint(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=RuntimeError("stage failed")),
        ):
            with self.assertRaises(RuntimeError):
                orchestration.execute_task("Plan existing child recovery", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        child_id = execution["linked_session"]["id"]
        child_path = self.root / "workspace" / "executions" / "runs" / child_id / "session.json"
        child_path.parent.mkdir(parents=True)
        child_path.write_text("{}", encoding="utf-8")
        outputs = [{"run_id": child_id, "role": "planner", "content": "resumed"}]
        with (
            patch.object(orchestration, "resume_sequence", return_value=outputs) as resume,
            patch.object(orchestration, "run_sequence") as start,
        ):
            result = orchestration.resume_orchestration_execution(execution["execution_id"])
        resume.assert_called_once_with(child_id)
        start.assert_not_called()
        self.assertEqual(result["execution"]["status"], "completed")

    def test_reconcile_completed_child_without_provider_work(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=KeyboardInterrupt("after child")),
        ):
            with self.assertRaises(KeyboardInterrupt):
                orchestration.execute_task("Plan reconciliation", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        child_id = str(execution["linked_session"]["id"])
        child_path = self.root / "workspace" / "executions" / "runs" / child_id / "session.json"
        child_path.parent.mkdir(parents=True)
        child_path.write_text("{}", encoding="utf-8")
        with (
            patch.object(
                orchestration, "_load_child_session", return_value={"run_id": child_id, "status": "completed"}
            ),
            patch.object(orchestration, "resume_sequence") as resume,
        ):
            reconciled = orchestration.reconcile_orchestration_execution(execution["execution_id"])
        resume.assert_not_called()
        self.assertEqual(reconciled["status"], "completed")
        self.assertEqual(reconciled["linked_session"]["status"], "completed")

    def test_reconcile_child_failure_keeps_wrapper_unresolved(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_debate_rounds", side_effect=KeyboardInterrupt("after child")),
        ):
            with self.assertRaises(KeyboardInterrupt):
                orchestration.execute_task("Compare API designs", stage="debate")
        execution = orchestration.load_orchestration_execution("latest")
        child_id = str(execution["linked_session"]["id"])
        child_path = self.root / "workspace" / "debates" / child_id / "session.json"
        child_path.parent.mkdir(parents=True)
        child_path.write_text("{}", encoding="utf-8")
        with patch.object(
            orchestration,
            "_load_child_session",
            return_value={"session_id": child_id, "status": "budget_exhausted", "error": "limit"},
        ):
            reconciled = orchestration.reconcile_orchestration_execution(execution["execution_id"])
        self.assertEqual(reconciled["status"], "failed")
        self.assertEqual(reconciled["error"], "limit")

    def test_reconcile_missing_child_marks_link_not_started(self) -> None:
        with (
            patch.object(orchestration, "load_services", return_value=self.services()),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=KeyboardInterrupt("before child")),
        ):
            with self.assertRaises(KeyboardInterrupt):
                orchestration.execute_task("Plan missing child", stage="planning")
        execution = orchestration.load_orchestration_execution("latest")
        reconciled = orchestration.reconcile_orchestration_execution(execution["execution_id"])
        self.assertEqual(reconciled["status"], "running")
        self.assertEqual(reconciled["linked_session"]["status"], "not_started")

    def test_execution_id_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid orchestration execution id"):
            orchestration.load_orchestration_execution("../outside")


if __name__ == "__main__":
    unittest.main()
