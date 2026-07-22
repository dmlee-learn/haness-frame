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

from haness_frame_app.templates.runtime import debate, orchestration, repair, storage, workflow
from haness_frame_app.templates.runtime.session_overview import session_overview


class SessionOverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.patcher = patch.object(storage, "ROOT", self.root)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def write_session(self, relative: str, payload: object) -> None:
        path = self.root / relative / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def canonical_pipeline_session(
        run_id: str, roles: list[str], prompt: str, system: str, retries: int = 1
    ) -> dict[str, object]:
        options = {"temperature": 0.2, "max_tokens": None, "retries": retries}
        limits: dict[str, object] = {}
        results = []
        for index, role in enumerate(roles, start=1):
            content = f"output-{index}"
            item: dict[str, object] = {
                "run_id": run_id,
                "index": index,
                "role": role,
                "prompt": prompt,
                "content": content,
                "content_sha256": workflow._sha256_text(content),
                "service": {"model": "fixture"},
            }
            item["result_sha256"] = workflow._result_sha256(item)
            results.append(item)
        return {
            "format_version": 2,
            "run_id": run_id,
            "status": "completed",
            "updated_at": "2026-07-20T15:02:00+00:00",
            "roles": roles,
            "results": results,
            "prompt": prompt,
            "system": system,
            "options": options,
            "limits": limits,
            "input_sha256": workflow._input_sha256(roles, prompt, system, options, limits),
            "error": "",
        }

    @staticmethod
    def pipeline_session(run_id: str, status: str, updated_at: str) -> dict[str, object]:
        roles = ["planner", "critic"]
        prompt = "secret prompt"
        system = ""
        options: dict[str, object] = {}
        limits: dict[str, object] = {}
        result: dict[str, object] = {
            "run_id": run_id,
            "index": 1,
            "role": "planner",
            "prompt": prompt,
            "content": "secret output",
            "content_sha256": workflow._sha256_text("secret output"),
            "service": {"model": "fixture"},
        }
        result["result_sha256"] = workflow._result_sha256(result)
        results = [result] if status != "abandoned" else []
        if status == "completed":
            second: dict[str, object] = {
                "run_id": run_id,
                "index": 2,
                "role": "critic",
                "prompt": prompt,
                "content": "second secret output",
                "content_sha256": workflow._sha256_text("second secret output"),
                "service": {"model": "fixture"},
            }
            second["result_sha256"] = workflow._result_sha256(second)
            results.append(second)
        return {
            "format_version": 2,
            "run_id": run_id,
            "status": status,
            "updated_at": updated_at,
            "roles": roles,
            "results": results,
            "prompt": prompt,
            "system": system,
            "options": options,
            "limits": limits,
            "input_sha256": workflow._input_sha256(roles, prompt, system, options, limits),
            "error": "provider timeout" if status == "failed" else "",
        }

    @staticmethod
    def debate_session(session_id: str, updated_at: str) -> dict[str, object]:
        roles = ["planner"]
        round_record: dict[str, object] = {
            "round": 1,
            "outputs": [{"role": "planner", "content": "secret debate output"}],
        }
        round_record["round_sha256"] = debate._round_sha256(round_record)
        verdict = {"decision": "fixture"}
        report: dict[str, object] = {
            "format_version": 2,
            "session_id": session_id,
            "roles": roles,
            "rounds": [round_record],
            "verdict": verdict,
            "verdict_sha256": debate._verdict_sha256(verdict),
            "evidence_input_digest": "sha256:fixture",
            "participant_services": [],
            "judge_service": {},
            "actual_judge_independence": {},
        }
        report["judge_provenance_sha256"] = debate.judge_provenance_sha256(report)
        report["result_sha256"] = debate.debate_result_sha256(report)
        session: dict[str, object] = {
            "format_version": 3,
            "session_id": session_id,
            "status": "completed",
            "stage": "completed",
            "prompt": "secret debate prompt",
            "roles": roles,
            "rounds_requested": 1,
            "round_results": [round_record],
            "options": {},
            "limits": {},
            "budget": {},
            "evidence_input_digest": "sha256:fixture",
            "result": report,
            "updated_at": updated_at,
        }
        session["input_sha256"] = debate._debate_input_sha256(session)
        return session

    @staticmethod
    def repair_session(session_id: str, updated_at: str) -> dict[str, object]:
        session: dict[str, object] = {
            "format_version": 2,
            "session_id": session_id,
            "task": "secret repair task",
            "status": "attempts_exhausted",
            "max_attempts": 1,
            "attempts": [],
            "updated_at": updated_at,
        }
        session["session_sha256"] = repair.repair_session_sha256(session)
        return session

    def test_combines_sessions_without_prompt_or_output_content(self) -> None:
        self.write_session(
            "workspace/executions/runs/run-1",
            self.pipeline_session("run-1", "failed", "2026-07-20T10:00:00+00:00"),
        )
        self.write_session(
            "workspace/debates/debate-1",
            self.debate_session("debate-1", "2026-07-20T11:00:00+00:00"),
        )
        self.write_session(
            "workspace/repairs/repair-1",
            {
                "session_id": "repair-1",
                "status": "budget_exhausted",
                "updated_at": "2026-07-20T12:00:00+00:00",
                "attempts": [{}],
            },
        )

        report = session_overview()

        self.assertEqual(report["total_sessions"], 3)
        self.assertEqual(report["needs_attention"], 2)
        self.assertEqual([item["kind"] for item in report["sessions"]], ["repair", "debate", "pipeline"])
        serialized = json.dumps(report)
        self.assertNotIn("secret prompt", serialized)
        self.assertNotIn("secret output", serialized)
        failed = next(item for item in report["sessions"] if item["kind"] == "pipeline")
        self.assertIn("pipeline-resume", failed["next_action"])

    def test_completed_pipeline_provenance_tampering_requires_attention(self) -> None:
        payload = self.pipeline_session("run-tampered", "completed", "2026-07-20T13:00:00+00:00")
        payload["results"][0]["service"]["model"] = "tampered"
        self.write_session("workspace/executions/runs/run-tampered", payload)
        report = session_overview(unresolved_only=True)
        self.assertEqual(report["needs_attention"], 1)
        self.assertEqual(report["sessions"][0]["status"], "invalid_checkpoint")
        self.assertIn("provenance hash mismatch", report["sessions"][0]["failure_reason"])

    def test_completed_debate_round_tampering_requires_attention(self) -> None:
        payload = self.debate_session("debate-tampered", "2026-07-20T14:00:00+00:00")
        payload["round_results"][0]["outputs"][0]["content"] = "tampered"
        self.write_session("workspace/debates/debate-tampered", payload)
        report = session_overview(unresolved_only=True)
        self.assertEqual(report["needs_attention"], 1)
        self.assertEqual(report["sessions"][0]["status"], "invalid_checkpoint")
        self.assertIn("round #1 provenance hash mismatch", report["sessions"][0]["failure_reason"])

    def test_terminal_repair_tampering_requires_attention(self) -> None:
        session_id = "20260720T140000000000Z"
        payload = self.repair_session(session_id, "2026-07-20T14:00:00+00:00")
        payload["task"] = "tampered"
        self.write_session(f"workspace/repairs/{session_id}", payload)
        report = session_overview(unresolved_only=True)
        self.assertEqual(report["needs_attention"], 1)
        self.assertEqual(report["sessions"][0]["status"], "invalid_checkpoint")
        self.assertIn("provenance hash mismatch", report["sessions"][0]["failure_reason"])

    def test_unresolved_filter_reports_corrupt_checkpoint(self) -> None:
        self.write_session(
            "workspace/debates/resolved",
            self.debate_session("resolved", "2026-07-20T10:00:00Z"),
        )
        broken = self.root / "workspace" / "repairs" / "broken" / "session.json"
        broken.parent.mkdir(parents=True)
        broken.write_text("{broken", encoding="utf-8")

        report = session_overview(unresolved_only=True)

        self.assertEqual(report["total_sessions"], 2)
        self.assertEqual(report["returned"], 1)
        self.assertEqual(report["sessions"][0]["status"], "invalid_checkpoint")

    def test_limit_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 200"):
            session_overview(limit=0)
        with self.assertRaisesRegex(ValueError, "between 1 and 200"):
            session_overview(limit=201)

    def test_orchestration_wrapper_is_included_in_unresolved_sessions(self) -> None:
        self.write_session(
            "workspace/orchestration/executions/orchestration-20260720T100000000000Z",
            {
                "execution_id": "orchestration-20260720T100000000000Z",
                "status": "failed",
                "stage": "planning",
                "roles": ["planner", "critic"],
                "linked_session": {"kind": "pipeline", "id": "pipeline-one"},
            },
        )
        report = session_overview(unresolved_only=True)
        self.assertEqual(report["needs_attention"], 1)
        item = report["sessions"][0]
        self.assertEqual(item["kind"], "orchestration")
        self.assertIn("orchestrate-resume", item["next_action"])

    def test_terminal_orchestration_tampering_requires_attention(self) -> None:
        execution_id = "orchestration-20260720T150000000000Z"
        plan_id = "20260720T150000000000Z"
        task = "Plan a safe migration"
        plan_path = self.root / "workspace" / "orchestration" / f"{plan_id}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan: dict[str, object] = {"format_version": 2, "plan_id": plan_id, "task": task}
        plan["plan_sha256"] = orchestration.orchestration_plan_sha256(plan)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        payload: dict[str, object] = {
            "format_version": 2,
            "execution_id": execution_id,
            "plan_id": plan_id,
            "plan_sha256": plan["plan_sha256"],
            "task_sha256": workflow._sha256_text(task),
            "stage": "planning",
            "roles": ["planner"],
            "options": {"rounds": 2, "retries": 1, "max_attempts": None},
            "status": "completed",
            "linked_session": {"kind": "pipeline", "id": "pipeline-one", "status": "completed"},
            "error": "",
            "created_at": "2026-07-20T15:00:00+00:00",
            "updated_at": "2026-07-20T15:01:00+00:00",
        }
        payload["execution_sha256"] = orchestration.orchestration_execution_sha256(payload)
        payload["linked_session"]["id"] = "pipeline-tampered"  # type: ignore[index]
        self.write_session(f"workspace/orchestration/executions/{execution_id}", payload)

        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["kind"] == "orchestration")
        self.assertEqual(wrapper["status"], "invalid_checkpoint")
        self.assertIn("provenance hash mismatch", wrapper["failure_reason"])

    def test_completed_orchestration_with_missing_child_requires_attention(self) -> None:
        services = {
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

        def outputs(*args: object, **kwargs: object) -> list[dict[str, object]]:
            return [{"run_id": kwargs["run_id"], "role": "planner", "content": "plan"}]

        with (
            patch.object(orchestration, "load_services", return_value=services),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=outputs),
            patch.object(orchestration, "log_event"),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")

        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["id"] == result["execution_id"])
        self.assertEqual(wrapper["status"], "invalid_checkpoint")
        self.assertIn("child checkpoint is missing", wrapper["failure_reason"])

    def test_completed_orchestration_child_input_must_match_wrapper(self) -> None:
        services = {
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

        def outputs(*args: object, **kwargs: object) -> list[dict[str, object]]:
            return [{"run_id": kwargs["run_id"], "role": "planner", "content": "plan"}]

        with (
            patch.object(orchestration, "load_services", return_value=services),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=outputs),
            patch.object(orchestration, "log_event"),
        ):
            result = orchestration.execute_task("Plan a safe migration", stage="planning")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        child_id = str(execution["linked_session"]["id"])
        self.write_session(
            f"workspace/executions/runs/{child_id}",
            self.pipeline_session(child_id, "completed", "2026-07-20T15:02:00+00:00"),
        )

        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["id"] == result["execution_id"])
        self.assertEqual(wrapper["status"], "invalid_checkpoint")
        self.assertIn("child input hash does not match", wrapper["failure_reason"])

    def test_completed_orchestration_with_matching_canonical_child_is_resolved(self) -> None:
        services = {
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

        def outputs(*args: object, **kwargs: object) -> list[dict[str, object]]:
            return [{"run_id": kwargs["run_id"], "role": "planner", "content": "plan"}]

        task = "Plan a safe migration"
        with (
            patch.object(orchestration, "load_services", return_value=services),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=outputs),
            patch.object(orchestration, "log_event"),
        ):
            result = orchestration.execute_task(task, stage="planning")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        child_id = str(execution["linked_session"]["id"])
        roles = list(execution["roles"])
        system = "Produce an evidence-aware implementation plan with decisions, risks, and verification needs."
        options = {"temperature": 0.2, "max_tokens": None, "retries": 1}
        limits: dict[str, object] = {}
        results = []
        for index, role in enumerate(roles, start=1):
            item: dict[str, object] = {
                "run_id": child_id,
                "index": index,
                "role": role,
                "prompt": task,
                "content": f"output-{index}",
                "content_sha256": workflow._sha256_text(f"output-{index}"),
                "service": {"model": "fixture"},
            }
            item["result_sha256"] = workflow._result_sha256(item)
            results.append(item)
        self.write_session(
            f"workspace/executions/runs/{child_id}",
            {
                "format_version": 2,
                "run_id": child_id,
                "status": "completed",
                "updated_at": "2026-07-20T15:02:00+00:00",
                "roles": roles,
                "results": results,
                "prompt": task,
                "system": system,
                "options": options,
                "limits": limits,
                "input_sha256": workflow._input_sha256(roles, task, system, options, limits),
                "error": "",
            },
        )

        report = session_overview(unresolved_only=True)
        self.assertEqual(report["needs_attention"], 0)
        self.assertEqual(report["sessions"], [])

    def test_completed_orchestration_child_roles_must_match_wrapper(self) -> None:
        services = {
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

        def outputs(*args: object, **kwargs: object) -> list[dict[str, object]]:
            return [{"run_id": kwargs["run_id"], "role": "planner", "content": "plan"}]

        task = "Plan a safe migration"
        with (
            patch.object(orchestration, "load_services", return_value=services),
            patch.object(orchestration, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(orchestration, "run_sequence", side_effect=outputs),
            patch.object(orchestration, "log_event"),
        ):
            result = orchestration.execute_task(task, stage="planning")
        execution = orchestration.load_orchestration_execution(result["execution_id"])
        child_id = str(execution["linked_session"]["id"])
        child_roles = list(execution["roles"][:-1])
        self.write_session(
            f"workspace/executions/runs/{child_id}",
            self.canonical_pipeline_session(
                child_id, child_roles, task, orchestration.PLANNING_SYSTEM
            ),
        )

        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["id"] == result["execution_id"])
        self.assertEqual(wrapper["status"], "invalid_checkpoint")
        self.assertIn("child roles do not match", wrapper["failure_reason"])

    def test_orchestration_with_terminal_child_recommends_reconcile(self) -> None:
        execution_id = "orchestration-20260720T100000000000Z"
        self.write_session(
            f"workspace/orchestration/executions/{execution_id}",
            {
                "execution_id": execution_id,
                "status": "running",
                "linked_session": {"kind": "debate", "id": "debate-one", "status": "completed"},
            },
        )
        self.write_session(
            "workspace/debates/debate-one",
            self.debate_session("debate-one", "2026-07-20T12:00:00+00:00"),
        )
        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["kind"] == "orchestration")
        self.assertIn("orchestrate-reconcile", wrapper["next_action"])

    def test_reconciled_terminal_failure_recommends_abandon(self) -> None:
        execution_id = "orchestration-20260720T100000000000Z"
        self.write_session(
            f"workspace/orchestration/executions/{execution_id}",
            {
                "execution_id": execution_id,
                "status": "failed",
                "linked_session": {
                    "kind": "repair", "id": "repair-one", "status": "attempts_exhausted"
                },
            },
        )
        self.write_session(
            "workspace/repairs/repair-one",
            {"session_id": "repair-one", "status": "attempts_exhausted"},
        )
        report = session_overview(unresolved_only=True)
        wrapper = next(item for item in report["sessions"] if item["kind"] == "orchestration")
        self.assertIn("orchestrate-abandon", wrapper["next_action"])


if __name__ == "__main__":
    unittest.main()
