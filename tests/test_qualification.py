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

from haness_frame_app.templates.runtime import audit, qualification, storage, workflow


class QualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "workspace" / "repair-policy.json").write_text(
            json.dumps({"editable_roots": ["src", "tests"], "require_independent_reviewer_service": False}),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(qualification, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_pipeline_session(self, name: str, status: str, updated_at: str) -> None:
        roles = ["planner"]
        prompt = "fixture prompt"
        system = ""
        options: dict[str, object] = {}
        limits: dict[str, object] = {}
        results: list[dict[str, object]] = []
        if status == "completed":
            content = "completed fixture output"
            results.append(
                {
                    "index": 1,
                    "role": "planner",
                    "content": content,
                    "content_sha256": workflow._sha256_text(content),
                }
            )
        payload = {
            "format_version": 1,
            "run_id": name,
            "status": status,
            "updated_at": updated_at,
            "roles": roles,
            "results": results,
            "prompt": prompt,
            "system": system,
            "options": options,
            "limits": limits,
            "input_sha256": workflow._input_sha256(roles, prompt, system, options, limits),
        }
        path = self.root / "workspace" / "executions" / "runs" / name / "session.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_qualified_report_runs_requested_verification(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": True, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(qualification, "run_verification_commands", return_value={"passed": True}) as verify,
        ):
            report = qualification.qualification_report(run_verification=True)
        self.assertTrue(report["qualified"])
        self.assertEqual(report["status"], "qualified")
        verify.assert_called_once_with()
        self.assertTrue((self.root / "workspace" / "qualifications" / "latest.json").is_file())

    def test_closed_gate_skips_verification_and_reports_component_failures(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": False, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": False, "issues": ["two sources required"]}),
            patch.object(
                qualification,
                "decision_gate",
                return_value={"allowed": False, "issues": ["two sources required", "decision required"]},
            ),
            patch.object(qualification, "run_verification_commands") as verify,
        ):
            report = qualification.qualification_report(run_verification=True)
        self.assertFalse(report["qualified"])
        self.assertTrue(report["verification"]["skipped"])
        self.assertIn("service validation failed", report["issues"])
        self.assertEqual(report["issues"].count("evidence: two sources required"), 1)
        self.assertNotIn("decision: two sources required", report["issues"])
        verify.assert_not_called()

    def test_service_configuration_issue_is_preserved_in_qualification(self) -> None:
        service_report = {
            "valid": False,
            "configuration_issues": ["workspace/services.json root must be a JSON object"],
            "unassigned_roles": [],
            "services": [],
        }
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value=service_report),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("service: workspace/services.json root must be a JSON object", report["issues"])

    def test_invalid_audit_log_blocks_qualification_without_exporting_records(self) -> None:
        audit_path = self.root / audit.AUDIT_LOG
        audit_path.parent.mkdir(parents=True)
        audit_path.write_text("not-json\n", encoding="utf-8")
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(
                qualification,
                "check_services",
                return_value={"valid": True, "unassigned_roles": [], "services": []},
            ),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("audit: line 1: invalid JSON", report["issues"][0])
        self.assertNotIn("records", report["audit"])

    def test_invalid_scorecard_blocks_qualification_without_overwriting_it(self) -> None:
        path = self.root / "workspace" / "scorecard.json"
        original = '{"private-value":'
        path.write_text(original, encoding="utf-8")
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(
                qualification,
                "check_services",
                return_value={"valid": True, "unassigned_roles": [], "services": []},
            ),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("scorecard: workspace/scorecard.json contains invalid JSON", report["issues"][0])
        self.assertNotIn("private-value", json.dumps(report))
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_ready_without_verification_is_not_claimed_as_qualified(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": True, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            report = qualification.qualification_report(run_verification=False)
        self.assertTrue(report["ready"])
        self.assertFalse(report["qualified"])
        self.assertEqual(report["status"], "ready")
        self.assertIn("--run-verification", report["next_actions"][0])

    def test_reviewer_independence_warning_does_not_block_readiness(self) -> None:
        services = {
            "valid": True,
            "unassigned_roles": [],
            "services": [],
            "warnings": ["coder and reviewer share the same provider endpoint and model"],
        }
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value=services),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
        ):
            report = qualification.qualification_report(run_verification=False)
        self.assertTrue(report["ready"])
        self.assertIn("service: coder and reviewer share", report["warnings"][0])
        self.assertIn("service: coder and reviewer share", report["next_actions"][1])

    def test_strict_reviewer_independence_blocks_repair_readiness(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy_path.write_text(
            json.dumps({"editable_roots": ["src"], "require_independent_reviewer_service": True}),
            encoding="utf-8",
        )
        with patch.object(
            qualification,
            "review_independence",
            return_value={
                "assessed": True,
                "independent_service": False,
                "reason": "coder and reviewer share provider endpoint and model",
            },
        ):
            report = qualification.repair_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "configuration_blocked")
        self.assertIn("independent reviewer service is required", report["issues"][0])

    def test_strict_policy_revalidates_actual_identity_in_approved_checkpoint(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy_path.write_text(
            json.dumps({"editable_roots": ["src"], "require_independent_reviewer_service": True}),
            encoding="utf-8",
        )
        actual = {
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "shared-fallback",
        }
        session = {
            "session_id": "20260720T120000000000Z",
            "status": "approved",
            "attempts": [
                {
                    "attempt": 1,
                    "status": "approved",
                    "coder_service": actual,
                    "reviewer_service": actual,
                }
            ],
        }
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=True),
            patch.object(qualification, "load_repair_session", return_value=session),
            patch.object(
                qualification,
                "review_independence",
                return_value={"assessed": True, "independent_service": True, "reason": "configured distinct"},
            ),
        ):
            report = qualification.repair_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "approved")
        self.assertIn("same actual coder/reviewer", report["issues"][0])
        self.assertFalse(report["actual_review_independence"]["independent_service"])

    def test_strict_policy_accepts_durable_distinct_actual_identities(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy_path.write_text(
            json.dumps({"editable_roots": ["src"], "require_independent_reviewer_service": True}),
            encoding="utf-8",
        )
        coder = {"provider_type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "coder"}
        reviewer = {**coder, "model": "reviewer"}
        approved_attempt = {
            "attempt": 1,
            "status": "approved",
            "coder_service": coder,
            "reviewer_service": reviewer,
            "reviewer": {"approved": True, "reason": "verified", "risks": []},
        }
        approved_attempt["review_provenance_sha256"] = qualification.review_provenance_sha256(approved_attempt)
        session = {
            "session_id": "20260720T120000000001Z",
            "status": "approved",
            "attempts": [approved_attempt],
        }
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=True),
            patch.object(qualification, "load_repair_session", return_value=session),
            patch.object(
                qualification,
                "review_independence",
                return_value={"assessed": True, "independent_service": True, "reason": "configured distinct"},
            ),
        ):
            report = qualification.repair_health_report()
        self.assertTrue(report["valid"])
        self.assertTrue(report["actual_review_independence"]["independent_service"])

    def test_strict_policy_rejects_tampered_review_provenance(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy_path.write_text(
            json.dumps({"editable_roots": ["src"], "require_independent_reviewer_service": True}),
            encoding="utf-8",
        )
        coder = {"provider_type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "coder"}
        reviewer = {**coder, "model": "reviewer"}
        attempt = {
            "attempt": 1,
            "status": "approved",
            "coder_service": coder,
            "reviewer_service": reviewer,
            "reviewer": {"approved": True, "reason": "original", "risks": []},
        }
        attempt["review_provenance_sha256"] = qualification.review_provenance_sha256(attempt)
        attempt["reviewer"]["reason"] = "tampered"
        session = {"session_id": "20260720T120000000002Z", "status": "approved", "attempts": [attempt]}
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=True),
            patch.object(qualification, "load_repair_session", return_value=session),
            patch.object(
                qualification,
                "review_independence",
                return_value={"assessed": True, "independent_service": True, "reason": "configured distinct"},
            ),
        ):
            report = qualification.repair_health_report()
        self.assertFalse(report["valid"])
        self.assertIn("provenance hash mismatch", report["issues"][-1])

    def test_failed_pipeline_blocks_readiness_until_resolved(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": True, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(
                qualification,
                "orchestration_health_report",
                return_value={"valid": False, "status": "failed", "issues": ["latest pipeline is failed"]},
            ),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("orchestration: latest pipeline is failed", report["issues"])

    def test_invalid_orchestration_policy_is_reported(self) -> None:
        (self.root / "workspace" / "orchestration-policy.json").write_text("not-json", encoding="utf-8")
        report = qualification.orchestration_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "invalid_policy")
        self.assertIn("invalid orchestration policy JSON", report["issues"][0])

    def test_abandoned_pipeline_is_a_resolved_health_state(self) -> None:
        with patch.object(
            qualification,
            "load_pipeline_session",
            return_value={
                "run_id": "pipeline-test",
                "status": "abandoned",
                "roles": ["planner"],
                "results": [],
                "budget": {"ai_calls": 1},
            },
        ):
            (self.root / qualification.LATEST_SESSION).parent.mkdir(parents=True)
            (self.root / qualification.LATEST_SESSION).write_text("{}", encoding="utf-8")
            report = qualification.orchestration_health_report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["status"], "abandoned")

    def test_failed_debate_blocks_readiness(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": True, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(
                qualification,
                "debate_health_report",
                return_value={"valid": False, "status": "failed", "issues": ["latest debate is failed"]},
            ),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("debate: latest debate is failed", report["issues"])

    def test_strict_judge_policy_revalidates_completed_debate_provenance(self) -> None:
        (self.root / "workspace" / "orchestration-policy.json").write_text(
            json.dumps({"require_independent_debate_judge_service": True}), encoding="utf-8"
        )
        result = {
            "verdict_sha256": "a" * 64,
            "evidence_input_digest": "sha256:" + "b" * 64,
            "participant_services": [
                {"provider_type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "planner"}
            ],
            "judge_service": {
                "provider_type": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "model": "judge",
            },
            "actual_judge_independence": {
                "assessed": True,
                "independent_service": True,
                "reason": "distinct",
            },
        }
        result["judge_provenance_sha256"] = qualification.judge_provenance_sha256(result)
        session = {
            "session_id": "debate-strict",
            "status": "completed",
            "round_results": [{}],
            "rounds_requested": 1,
            "result": result,
        }
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=True),
            patch.object(qualification, "load_debate_session", return_value=session),
            patch.object(
                qualification,
                "debate_judge_independence",
                return_value={"assessed": True, "independent_service": True, "reason": "configured distinct"},
            ),
        ):
            report = qualification.debate_health_report()
        self.assertTrue(report["valid"])
        result["judge_service"]["model"] = "planner"
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=True),
            patch.object(qualification, "load_debate_session", return_value=session),
            patch.object(
                qualification,
                "debate_judge_independence",
                return_value={"assessed": True, "independent_service": True, "reason": "configured distinct"},
            ),
        ):
            tampered = qualification.debate_health_report()
        self.assertFalse(tampered["valid"])
        self.assertIn("provenance hash mismatch", tampered["issues"][-1])

    def test_strict_judge_policy_blocks_before_debate_starts(self) -> None:
        (self.root / "workspace" / "orchestration-policy.json").write_text(
            json.dumps({"require_independent_debate_judge_service": True}), encoding="utf-8"
        )
        with (
            patch.object(qualification, "_has_session_checkpoint", return_value=False),
            patch.object(
                qualification,
                "debate_judge_independence",
                return_value={
                    "assessed": True,
                    "independent_service": False,
                    "reason": "judge shares configured participant identity",
                    "shared_roles": ["planner"],
                },
            ),
        ):
            report = qualification.debate_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "configuration_blocked")

    def test_abandoned_debate_is_a_resolved_health_state(self) -> None:
        with patch.object(
            qualification,
            "load_debate_session",
            return_value={
                "session_id": "debate-test",
                "status": "abandoned",
                "stage": "judge",
                "round_results": [],
                "rounds_requested": 1,
            },
        ):
            path = self.root / qualification.LATEST_DEBATE_SESSION
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            report = qualification.debate_health_report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["status"], "abandoned")

    def test_failed_repair_blocks_readiness(self) -> None:
        with (
            patch.object(qualification.compileall, "compile_dir", return_value=True),
            patch.object(qualification, "validate_manifest", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "check_services", return_value={"valid": True, "unassigned_roles": [], "services": []}),
            patch.object(qualification, "evidence_policy_report", return_value={"valid": True, "issues": []}),
            patch.object(qualification, "decision_gate", return_value={"allowed": True, "issues": []}),
            patch.object(
                qualification,
                "repair_health_report",
                return_value={"valid": False, "status": "attempts_exhausted", "issues": ["latest repair is attempts_exhausted"]},
            ),
        ):
            report = qualification.qualification_report()
        self.assertFalse(report["ready"])
        self.assertIn("repair: latest repair is attempts_exhausted", report["issues"])

    def test_abandoned_repair_is_a_resolved_health_state(self) -> None:
        with patch.object(
            qualification,
            "load_repair_session",
            return_value={
                "session_id": "20260719T000000000017Z",
                "status": "abandoned",
                "attempts": [],
                "budget": {"ai_calls": 1},
            },
        ):
            path = self.root / qualification.REPAIR_ROOT / "latest.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            report = qualification.repair_health_report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["status"], "abandoned")

    def test_older_failed_session_cannot_be_hidden_by_newer_completion(self) -> None:
        self.write_pipeline_session("pipeline-old", "failed", "2026-07-20T10:00:00Z")
        self.write_pipeline_session("pipeline-new", "completed", "2026-07-20T11:00:00Z")

        report = qualification.execution_history_health_report()

        self.assertFalse(report["valid"])
        self.assertEqual(report["needs_attention"], 1)
        self.assertIn("pipeline pipeline-old is failed", report["issues"])
        self.assertTrue(any("runs --unresolved" in issue for issue in report["issues"]))

    def test_resolved_session_history_is_valid(self) -> None:
        for name, status in (("pipeline-one", "completed"), ("pipeline-two", "abandoned")):
            self.write_pipeline_session(name, status, "2026-07-20T12:00:00Z")
        repair_path = self.root / "workspace" / "repairs" / "20260719T000000000019Z" / "session.json"
        repair_path.parent.mkdir(parents=True)
        repair_path.write_text(
            json.dumps(
                {
                    "session_id": "20260719T000000000019Z",
                    "status": "superseded",
                    "successor_session_id": "20260719T000000000020Z",
                    "attempts": [],
                }
            ),
            encoding="utf-8",
        )
        report = qualification.execution_history_health_report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["needs_attention"], 0)

    def test_corrupt_debate_checkpoint_is_reported(self) -> None:
        path = self.root / qualification.LATEST_DEBATE_SESSION
        path.parent.mkdir(parents=True)
        path.write_text("not-json", encoding="utf-8")
        report = qualification.debate_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "invalid_checkpoint")

    def test_missing_pipeline_latest_pointer_uses_durable_session(self) -> None:
        path = self.root / qualification.RUN_ROOT / "pipeline-recovered" / "session.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        report = qualification.orchestration_health_report()
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "invalid_checkpoint")


if __name__ == "__main__":
    unittest.main()
