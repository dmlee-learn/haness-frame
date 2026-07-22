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

from haness_frame_app.templates.runtime import audit, debate, storage


class DebateRoundTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
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
    def verdict() -> dict[str, object]:
        return {
            "decision": "option-a",
            "rationale": "best fit",
            "agreements": ["scope"],
            "disagreements": ["storage"],
            "risks": ["migration"],
            "confidence": "medium",
            "implementation_brief": ["Implement option A behind the existing boundary."],
            "verification_commands": ["python -m unittest"],
            "claim_ids": [],
        }

    def test_rounds_pass_prior_outputs_to_next_round_and_save_verdict(self) -> None:
        prompts: list[str] = []

        def fake_sequence(roles: list[str], prompt: str, **kwargs: object) -> list[dict[str, object]]:
            prompts.append(prompt)
            return [{"role": roles[0], "content": f"position {len(prompts)}"}]

        verdict = self.verdict()
        with (
            patch.object(debate, "run_sequence", side_effect=fake_sequence),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(verdict)}),
        ):
            report = debate.run_debate_rounds("Choose design", roles=["planner"], rounds=2)

        self.assertEqual(len(prompts), 2)
        self.assertNotIn("position 1", prompts[0])
        self.assertIn("position 1", prompts[1])
        self.assertEqual(report["verdict"]["decision"], "option-a")
        self.assertEqual(report["verdict_sha256"], debate._verdict_sha256(verdict))
        self.assertRegex(report["judge_provenance_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(str(report["evidence_input_digest"]).startswith("sha256:"))
        self.assertTrue((self.root / "workspace" / "debates" / "latest.json").exists())

    def test_round_and_judge_prompts_bound_large_role_outputs(self) -> None:
        rounds = [
            {
                "round": number,
                "outputs": [
                    {"role": role, "content": f"{role}-start " + ("x" * 30000) + f" {role}-end"}
                    for role in ("planner", "designer", "architect", "critic")
                ],
            }
            for number in (1, 2)
        ]
        round_prompt = debate._round_prompt("Choose design", rounds[:1], 20000)
        judge_prompt = debate._judge_prompt("Choose design", rounds, 20000)
        self.assertLessEqual(len(round_prompt), 20000)
        self.assertLessEqual(len(judge_prompt), 20000)
        self.assertIn("planner-start", round_prompt)
        self.assertIn("critic-end", round_prompt)
        self.assertIn("...[truncated]...", judge_prompt)

    def test_parse_judge_normalizes_single_string_collection_fields(self) -> None:
        verdict = self.verdict()
        verdict["implementation_brief"] = "Implement the selected design."
        verdict["agreements"] = "Keep the command interface small."

        parsed = debate._parse_judge(json.dumps(verdict))

        self.assertEqual(parsed["implementation_brief"], ["Implement the selected design."])
        self.assertEqual(parsed["agreements"], ["Keep the command interface small."])

    def test_judge_prompt_lists_accepted_claim_ids(self) -> None:
        evidence_dir = self.root / "workspace" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "claim-evidence.json").write_text(
            json.dumps(
                [
                    {"claim_id": "claim-accepted", "claim": "Use the documented interface.", "status": "accepted"},
                    {"claim_id": "claim-rejected", "claim": "Use a private API.", "status": "rejected"},
                ]
            ),
            encoding="utf-8",
        )

        prompt = debate._judge_prompt("Choose design", [], 20000)

        self.assertIn("claim-accepted", prompt)
        self.assertNotIn("claim-rejected", prompt)
        self.assertIn("never invent an ID", prompt)

    def test_judge_prompt_bounds_large_original_question(self) -> None:
        prompt = debate._judge_prompt("question " * 10000, [], 20000)

        self.assertLessEqual(len(prompt), 20000)
        self.assertIn("Accepted claims:", prompt)

    def test_judge_uses_minimum_structured_output_token_budget(self) -> None:
        verdict = self.verdict()
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "position"}]),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(verdict)}) as judge,
        ):
            debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1, max_tokens=128)

        self.assertEqual(judge.call_args.kwargs["max_tokens"], 512)

    def test_latest_verdict_rejects_tampered_judge_provenance(self) -> None:
        outputs = [{"role": "planner", "content": "position"}]
        with (
            patch.object(debate, "run_sequence", return_value=outputs),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        latest_path = self.root / "workspace" / "debates" / "latest.json"
        report = json.loads(latest_path.read_text(encoding="utf-8"))
        report["judge_service"] = {
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "tampered",
        }
        latest_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "judge provenance hash mismatch"):
            debate.load_latest_debate_verdict()

    def test_debate_session_rejects_tampered_round_provenance(self) -> None:
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "position"}]),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            report = debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        path = self.root / "workspace" / "debates" / str(report["session_id"]) / "session.json"
        session = json.loads(path.read_text(encoding="utf-8"))
        session["round_results"][0]["outputs"][0]["content"] = "tampered position"
        path.write_text(json.dumps(session), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "round #1 provenance hash mismatch"):
            debate.load_debate_session(str(report["session_id"]))

    def test_latest_verdict_rejects_tampered_full_result_provenance(self) -> None:
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "position"}]),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        latest_path = self.root / "workspace" / "debates" / "latest.json"
        report = json.loads(latest_path.read_text(encoding="utf-8"))
        report["actual_judge_independence"]["reason"] = "tampered reason"
        latest_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "result provenance hash mismatch"):
            debate.load_latest_debate_verdict()

    def test_strict_judge_policy_blocks_shared_configured_identity(self) -> None:
        service = {
            "name": "shared",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "same-model",
        }
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"planner": service, "decision_maker": dict(service)}}),
            encoding="utf-8",
        )
        limits = {
            "max_debate_rounds": 5,
            "max_debate_elapsed_seconds": 3600,
            "max_debate_ai_calls": 32,
            "require_independent_debate_judge_service": True,
        }
        with (
            patch.object(debate, "load_orchestration_policy", return_value=limits),
            patch.object(debate, "run_sequence") as rounds,
        ):
            with self.assertRaisesRegex(RuntimeError, "independent debate judge service is required"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        rounds.assert_not_called()

    def test_strict_judge_policy_blocks_shared_actual_fallback_identity(self) -> None:
        planner = {
            "name": "planner",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "planner-model",
        }
        judge = {**planner, "name": "judge", "model": "judge-model"}
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"planner": planner, "decision_maker": judge}}),
            encoding="utf-8",
        )
        limits = {
            "max_debate_rounds": 5,
            "max_debate_elapsed_seconds": 3600,
            "max_debate_ai_calls": 32,
            "require_independent_debate_judge_service": True,
        }
        actual = {
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "shared-fallback",
        }
        outputs = [{"role": "planner", "service": actual, "content": "position"}]
        with (
            patch.object(debate, "load_orchestration_policy", return_value=limits),
            patch.object(debate, "run_sequence", return_value=outputs),
            patch.object(
                debate,
                "invoke_cached",
                return_value={"service": actual, "content": json.dumps(self.verdict())},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "shared an actual participant identity"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        session = debate.load_debate_session("latest")
        self.assertEqual(session["status"], "failed")
        self.assertFalse(session["actual_judge_independence"]["independent_service"])

    def test_debate_audit_does_not_store_prompt_text(self) -> None:
        prompt = "Sensitive product decision details"
        with patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "A detailed role response."}]):
            debate.run_debate(prompt, roles=["planner"])
        audit_text = (self.root / "workspace" / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(prompt, audit_text)
        self.assertIn("prompt_sha256", audit_text)

    def test_judge_requires_all_structured_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            debate._parse_judge('{"decision": "a"}')

    def test_round_count_is_bounded(self) -> None:
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "x"}]) as sequence,
            patch.object(
                debate,
                "invoke_cached",
                return_value={
                    "content": json.dumps(
                        {
                            "decision": "a",
                            "rationale": "r",
                            "agreements": [],
                            "disagreements": [],
                            "risks": [],
                            "confidence": "low",
                            "implementation_brief": ["Document the selected option."],
                            "verification_commands": ["python -m compileall src"],
                            "claim_ids": [],
                        }
                    )
                },
            ),
        ):
            debate.run_debate_rounds("Choose", roles=["planner"], rounds=99)
        self.assertEqual(sequence.call_count, 5)

    def test_failed_round_resumes_linked_pipeline_without_repeating_round(self) -> None:
        current_prompt: list[str] = []

        def fail_round(roles: list[str], prompt: str, **kwargs: object) -> list[dict[str, object]]:
            current_prompt.append(prompt)
            raise RuntimeError("round provider failed")

        pipeline = {"run_id": "pipeline-round", "prompt": "", "roles": ["planner"]}
        with (
            patch.object(debate, "run_sequence", side_effect=fail_round) as run_round,
            patch.object(debate, "load_pipeline_session", side_effect=lambda _: {**pipeline, "prompt": current_prompt[-1]}),
        ):
            with self.assertRaisesRegex(RuntimeError, "round provider failed"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        session = debate.load_debate_session("latest")
        self.assertEqual(session["status"], "failed")
        self.assertEqual(session["active_pipeline_run_id"], "pipeline-round")

        outputs = [{"run_id": "pipeline-round", "role": "planner", "content": "A recovered detailed position."}]
        with (
            patch.object(debate, "resume_sequence", return_value=outputs) as resume_round,
            patch.object(debate, "run_sequence") as repeat_round,
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            report = debate.resume_debate_rounds(str(session["session_id"]))
        self.assertEqual(report["verdict"]["decision"], "option-a")
        resume_round.assert_called_once_with("pipeline-round")
        repeat_round.assert_not_called()
        self.assertEqual(run_round.call_count, 1)

    def test_failed_judge_resumes_without_repeating_completed_round(self) -> None:
        outputs = [{"run_id": "pipeline-ok", "role": "planner", "content": "A complete detailed position."}]
        with (
            patch.object(debate, "run_sequence", return_value=outputs) as run_round,
            patch.object(debate, "invoke_cached", side_effect=RuntimeError("judge unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        session = debate.load_debate_session("latest")
        self.assertEqual(session["stage"], "judge")
        self.assertEqual(session["budget"]["ai_calls"], 2)
        with (
            patch.object(debate, "run_sequence") as repeat_round,
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}) as judge,
        ):
            report = debate.resume_debate_rounds(str(session["session_id"]))
        repeat_round.assert_not_called()
        judge.assert_called_once()
        self.assertEqual(report["verdict_sha256"], debate._verdict_sha256(self.verdict()))
        self.assertEqual(run_round.call_count, 1)
        completed = debate.load_debate_session(str(session["session_id"]))
        self.assertEqual(completed["budget"]["ai_calls"], 3)

    def test_debate_call_budget_is_terminal_and_survives_resume(self) -> None:
        limits = {
            "max_debate_rounds": 5,
            "max_debate_elapsed_seconds": 3600,
            "max_debate_ai_calls": 1,
        }
        outputs = [{"run_id": "pipeline-ok", "role": "planner", "content": "A detailed position."}]
        with (
            patch.object(debate, "load_orchestration_policy", return_value=limits),
            patch.object(debate, "run_sequence", return_value=outputs) as run_round,
            patch.object(debate, "invoke_cached") as judge,
        ):
            with self.assertRaisesRegex(RuntimeError, "AI-call budget exhausted"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=2)
        self.assertEqual(run_round.call_count, 1)
        judge.assert_not_called()
        session = debate.load_debate_session("latest")
        self.assertEqual(session["status"], "budget_exhausted")
        self.assertEqual(session["budget"]["ai_calls"], 1)

        with patch.object(debate, "run_sequence") as repeat_round, patch.object(debate, "invoke_cached") as judge:
            with self.assertRaisesRegex(RuntimeError, "terminal"):
                debate.resume_debate_rounds(str(session["session_id"]))
        repeat_round.assert_not_called()
        judge.assert_not_called()

    def test_failed_debate_can_be_abandoned_and_cannot_resume(self) -> None:
        outputs = [{"run_id": "pipeline-ok", "role": "planner", "content": "A detailed position."}]
        with (
            patch.object(debate, "run_sequence", return_value=outputs),
            patch.object(debate, "invoke_cached", side_effect=RuntimeError("judge unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        session = debate.load_debate_session("latest")
        session_id = str(session["session_id"])
        abandoned = debate.abandon_debate_rounds(session_id, "Superseded by corrected evidence")
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["abandonment_reason"], "Superseded by corrected evidence")
        self.assertEqual(debate.abandon_debate_rounds(session_id, "ignored"), abandoned)
        with self.assertRaisesRegex(RuntimeError, "terminal: abandoned"):
            debate.resume_debate_rounds(session_id)

    def test_completed_debate_cannot_be_abandoned(self) -> None:
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "A detailed position."}]),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            report = debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        with self.assertRaisesRegex(ValueError, "completed debate"):
            debate.abandon_debate_rounds(str(report["session_id"]), "No longer needed")

    def test_evidence_change_before_judge_is_terminal(self) -> None:
        evidence_path = self.root / "workspace" / "evidence" / "search-evidence.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("[]", encoding="utf-8")

        def change_evidence(*args: object, **kwargs: object) -> list[dict[str, object]]:
            evidence_path.write_text('[{"url":"https://example.com/changed"}]', encoding="utf-8")
            return [{"run_id": "pipeline-ok", "role": "planner", "content": "A detailed position."}]

        with patch.object(debate, "run_sequence", side_effect=change_evidence), patch.object(debate, "invoke_cached") as judge:
            with self.assertRaisesRegex(RuntimeError, "evidence snapshot changed"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        judge.assert_not_called()
        session = debate.load_debate_session("latest")
        self.assertEqual(session["status"], "stale")
        with self.assertRaisesRegex(RuntimeError, "terminal"):
            debate.resume_debate_rounds(str(session["session_id"]))

    def test_debate_session_input_hash_detects_corruption(self) -> None:
        with (
            patch.object(debate, "run_sequence", return_value=[{"role": "planner", "content": "A detailed position."}]),
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            report = debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        path = self.root / "workspace" / "debates" / str(report["session_id"]) / "session.json"
        session = json.loads(path.read_text(encoding="utf-8"))
        session["prompt"] = "tampered"
        path.write_text(json.dumps(session), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "input hash mismatch"):
            debate.load_debate_session(str(report["session_id"]))

    def test_legacy_failed_judge_session_migrates_and_resumes(self) -> None:
        outputs = [{"run_id": "pipeline-ok", "role": "planner", "content": "A detailed position."}]
        with (
            patch.object(debate, "run_sequence", return_value=outputs),
            patch.object(debate, "invoke_cached", side_effect=RuntimeError("judge unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                debate.run_debate_rounds("Choose design", roles=["planner"], rounds=1)
        current = debate.load_debate_session("latest")
        session_id = str(current["session_id"])
        legacy = dict(current)
        legacy["format_version"] = 1
        legacy.pop("limits")
        legacy.pop("budget")
        legacy.pop("round_budget_reserved")
        legacy.pop("judge_attempt_inflight")
        legacy["input_sha256"] = debate._legacy_debate_input_sha256(legacy)
        path = self.root / "workspace" / "debates" / session_id / "session.json"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = debate.load_debate_session(session_id)
        self.assertEqual(migrated["format_version"], 2)
        self.assertEqual(migrated["migrated_from_format_version"], 1)
        self.assertEqual(migrated["budget"]["ai_calls"], 2)
        with (
            patch.object(debate, "run_sequence") as repeat_round,
            patch.object(debate, "invoke_cached", return_value={"content": json.dumps(self.verdict())}),
        ):
            report = debate.resume_debate_rounds(session_id)
        repeat_round.assert_not_called()
        self.assertEqual(report["verdict"]["decision"], "option-a")
        completed = debate.load_debate_session(session_id)
        self.assertEqual(completed["budget"]["ai_calls"], 3)

    def test_tampered_legacy_session_is_rejected(self) -> None:
        legacy = {
            "format_version": 1,
            "session_id": "legacy-tampered",
            "status": "failed",
            "stage": "round_1",
            "prompt": "original",
            "roles": ["planner"],
            "rounds_requested": 1,
            "round_results": [],
            "options": {"temperature": 0.2, "max_tokens": None, "retries": 1},
            "evidence_input_digest": "sha256:legacy",
            "input_sha256": "invalid",
        }
        path = self.root / "workspace" / "debates" / "legacy-tampered" / "session.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(legacy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "input hash mismatch"):
            debate.load_debate_session("legacy-tampered")


if __name__ == "__main__":
    unittest.main()
