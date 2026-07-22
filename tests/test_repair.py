from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, repair, storage


class RepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir(parents=True)
        (self.root / "docs").mkdir(parents=True)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "src" / "sample.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "docs" / "03-decision-record.md").write_text("accepted", encoding="utf-8")
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "workspace" / "repair-policy.json").write_text(
            json.dumps(
                {
                    "editable_roots": ["src", "tests", "implementation"],
                    "max_attempts": 2,
                    "rollback_on_failure": True,
                    "max_context_files": 4,
                    "max_context_chars": 10000,
                }
            ),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(repair, "ROOT", self.root),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def failed_verification() -> dict[str, object]:
        return {
            "passed": False,
            "results": [
                {
                    "command": "python -m unittest",
                    "passed": False,
                    "returncode": 1,
                    "timed_out": False,
                    "stdout": "",
                    "stderr": "AssertionError",
                }
            ],
        }

    def test_extracts_fenced_unified_diff(self) -> None:
        content = "```diff\n--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-old\n+new\n```"
        self.assertTrue(repair.extract_unified_diff(content).startswith("--- a/src/sample.py"))

    def test_collect_context_rejects_outside_file(self) -> None:
        policy = json.loads((self.root / "workspace" / "repair-policy.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "outside editable roots"):
            repair.collect_file_context(["docs/03-decision-record.md"], policy)

    def test_strict_independent_reviewer_policy_blocks_shared_model(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["require_independent_reviewer_service"] = True
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        service = {
            "name": "local-ai",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "same-model",
            "enabled": True,
        }
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"coder": service, "reviewer": dict(service)}}),
            encoding="utf-8",
        )
        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "run_verification_commands") as verify,
        ):
            with self.assertRaisesRegex(RuntimeError, "independent reviewer service is required"):
                repair.run_repair_loop("Fix sample", max_attempts=1)
        verify.assert_not_called()

    def test_strict_independent_reviewer_policy_accepts_distinct_model(self) -> None:
        coder = {
            "name": "coder",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "coder-model",
        }
        reviewer = {**coder, "name": "reviewer", "model": "review-model"}
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"coder": coder, "reviewer": reviewer}}),
            encoding="utf-8",
        )
        repair._enforce_review_independence({"require_independent_reviewer_service": True})

    def test_strict_policy_rolls_back_when_actual_fallback_identity_is_shared(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["require_independent_reviewer_service"] = True
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        coder = {
            "name": "coder-primary",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "coder-model",
        }
        reviewer = {**coder, "name": "reviewer-primary", "model": "review-model"}
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"coder": coder, "reviewer": reviewer}}),
            encoding="utf-8",
        )
        actual = {
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "shared-fallback",
        }

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            if role == "debugger":
                return {"content": json.dumps({"diagnosis": "bad", "files": [], "strategy": "fix"})}
            if role == "coder":
                return {"service": actual, "content": "```diff\n--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-a\n+b\n```"}
            if role == "reviewer":
                return {
                    "service": actual,
                    "content": json.dumps({"approved": True, "reason": "ok", "risks": []}),
                }
            raise AssertionError(role)

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(
                repair,
                "run_verification_commands",
                side_effect=[self.failed_verification(), {"passed": True, "results": []}],
            ),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
            patch.object(repair, "apply_patch_text", return_value={"patch_id": "20260719T000000000109Z"}),
            patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback,
        ):
            session = repair.run_repair_loop("Fix fallback identity", max_attempts=1)
        self.assertEqual(session["status"], "attempts_exhausted")
        self.assertIn("shared actual", session["attempts"][0]["error"])
        rollback.assert_called_once()

    def test_repair_loop_reaches_independent_approval(self) -> None:
        passed = {"passed": True, "results": []}

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            if role == "debugger":
                return {"content": json.dumps({"diagnosis": "bad value", "files": ["src/sample.py"], "strategy": "change value"})}
            if role == "coder":
                return {"content": "```diff\n--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n```"}
            if role == "reviewer":
                return {"content": json.dumps({"approved": True, "reason": "tests pass", "risks": []})}
            raise AssertionError(role)

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "run_verification_commands", side_effect=[self.failed_verification(), passed]),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
            patch.object(repair, "apply_patch_text", return_value={"patch_id": "20260719T000000000000Z"}),
        ):
            session = repair.run_repair_loop("Fix sample", max_attempts=1)

        self.assertEqual(session["status"], "approved")
        self.assertEqual(session["attempts"][0]["status"], "approved")
        self.assertRegex(session["attempts"][0]["review_provenance_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue((self.root / "workspace" / "repairs" / "latest.json").exists())

    def test_failed_verification_rolls_back_and_exhausts_attempts(self) -> None:
        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            if role == "debugger":
                return {"content": json.dumps({"diagnosis": "bad value", "files": ["src/sample.py"], "strategy": "change value"})}
            if role == "coder":
                return {"content": "```diff\n--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n```"}
            raise AssertionError(role)

        failure = self.failed_verification()
        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "run_verification_commands", side_effect=[failure, failure]),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
            patch.object(repair, "apply_patch_text", return_value={"patch_id": "20260719T000000000000Z"}),
            patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback,
        ):
            session = repair.run_repair_loop("Fix sample", max_attempts=1)

        self.assertEqual(session["status"], "attempts_exhausted")
        self.assertEqual(session["attempts"][0]["status"], "verification_failed")
        rollback.assert_called_once()

    def test_ai_call_budget_stops_before_coder_and_records_reason(self) -> None:
        policy_path = self.root / "workspace" / "repair-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy.update({"max_ai_calls": 1, "max_elapsed_seconds": 60, "ai_max_tokens": 321})
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        calls: list[tuple[str, object]] = []

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            calls.append((role, kwargs.get("max_tokens")))
            return {
                "content": json.dumps(
                    {"diagnosis": "bad value", "files": ["src/sample.py"], "strategy": "change value"}
                )
            }

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "run_verification_commands", return_value=self.failed_verification()),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
        ):
            session = repair.run_repair_loop("Fix sample", max_attempts=2)

        self.assertEqual(session["status"], "budget_exhausted")
        self.assertEqual(session["attempts"][0]["status"], "budget_exhausted")
        self.assertIn("coder", session["budget"]["reason"])
        self.assertEqual(calls, [("debugger", 321)])

    def write_session(self, session: dict[str, object]) -> str:
        session_id = str(session["session_id"])
        path = self.root / "workspace" / "repairs" / session_id / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session), encoding="utf-8")
        (self.root / "workspace" / "repairs" / "latest.json").write_text(
            json.dumps(session),
            encoding="utf-8",
        )
        return session_id

    def test_format_two_session_hash_detects_metadata_tampering(self) -> None:
        session = {
            "format_version": 2,
            "session_id": "20260719T000000000030Z",
            "task": "original task",
            "status": "attempts_exhausted",
            "max_attempts": 1,
            "attempts": [],
        }
        session["session_sha256"] = repair.repair_session_sha256(session)
        session_id = self.write_session(session)
        self.assertEqual(repair.load_repair_session(session_id)["task"], "original task")
        path = self.root / "workspace" / "repairs" / session_id / "session.json"
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["task"] = "tampered task"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "provenance hash mismatch"):
            repair.load_repair_session(session_id)

    def test_resume_returns_terminal_session_without_repeating_work(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000000Z",
                "task": "done",
                "status": "approved",
                "max_attempts": 2,
                "attempts": [],
            }
        )
        with patch.object(repair, "run_repair_loop") as run_loop:
            session = repair.resume_repair_loop(session_id)
        self.assertEqual(session["status"], "approved")
        run_loop.assert_not_called()

    def test_resume_does_not_repeat_budget_exhausted_session(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000005Z",
                "task": "budgeted task",
                "status": "budget_exhausted",
                "max_attempts": 2,
                "attempts": [],
                "budget": {"reason": "AI-call budget exhausted"},
            }
        )
        with patch.object(repair, "run_repair_loop") as run_loop:
            session = repair.resume_repair_loop(session_id)
        self.assertEqual(session["status"], "budget_exhausted")
        run_loop.assert_not_called()

    def test_failed_repair_can_be_abandoned_and_cannot_resume(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000011Z",
                "task": "superseded task",
                "status": "attempts_exhausted",
                "max_attempts": 1,
                "attempts": [],
            }
        )

        abandoned = repair.abandon_repair_loop(session_id, "requirements changed")

        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["abandonment_reason"], "requirements changed")
        with self.assertRaisesRegex(RuntimeError, "terminal: abandoned"):
            repair.resume_repair_loop(session_id)
        audit_text = (self.root / "workspace" / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("requirements changed", audit_text)

    def test_abandon_rolls_back_active_patch(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000012Z",
                "task": "active patch",
                "status": "running",
                "max_attempts": 2,
                "attempts": [
                    {"attempt": 1, "status": "running", "patch": {"patch_id": "20260719T000000000013Z"}}
                ],
            }
        )
        with patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback:
            abandoned = repair.abandon_repair_loop(session_id, "stop this repair")
        rollback.assert_called_once_with("20260719T000000000013Z")
        self.assertTrue(abandoned["attempts"][0]["rollback"]["rolled_back"])
        self.assertEqual(abandoned["status"], "abandoned")

    def test_abandon_stays_blocked_when_patch_rollback_conflicts(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000014Z",
                "task": "conflicting patch",
                "status": "running",
                "max_attempts": 2,
                "attempts": [
                    {"attempt": 1, "status": "running", "patch": {"patch_id": "20260719T000000000015Z"}}
                ],
            }
        )
        with patch.object(repair, "rollback_patch", side_effect=ValueError("files changed after patch")):
            with self.assertRaisesRegex(RuntimeError, "rollback blocked"):
                repair.abandon_repair_loop(session_id, "stop this repair")
        saved = repair.load_repair_session(session_id)
        self.assertEqual(saved["status"], "rollback_blocked")

    def test_successful_repair_cannot_be_abandoned(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000016Z",
                "task": "successful task",
                "status": "approved",
                "max_attempts": 1,
                "attempts": [],
            }
        )
        with self.assertRaisesRegex(ValueError, "successful repair"):
            repair.abandon_repair_loop(session_id, "not needed")

    def test_resume_verifies_inflight_patch_without_repeating_debugger_or_coder(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000001Z",
                "task": "resume task",
                "status": "running",
                "max_attempts": 3,
                "budget": {"elapsed_seconds": 2.0, "ai_calls": 2},
                "initial_verification": self.failed_verification(),
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "patch": {"patch_id": "20260719T000000000002Z"},
                    }
                ],
            }
        )
        diff_path = self.root / "workspace" / "repairs" / session_id / "attempt-1.diff"
        diff_path.write_text("--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n", encoding="utf-8")
        roles: list[str] = []

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            roles.append(role)
            return {"content": json.dumps({"approved": True, "reason": "passes", "risks": []})}

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "patch_state", return_value={"state": "applied", "conflicts": []}),
            patch.object(repair, "run_verification_commands", return_value={"passed": True, "results": []}) as verify,
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
            patch.object(repair, "rollback_patch") as rollback,
            patch.object(repair, "run_repair_loop") as run_loop,
        ):
            result = repair.resume_repair_loop(session_id, retries=2)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(roles, ["reviewer"])
        verify.assert_called_once_with()
        rollback.assert_not_called()
        run_loop.assert_not_called()

    def test_resume_finalizes_saved_approval_without_external_work(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000006Z",
                "task": "resume task",
                "status": "running",
                "max_attempts": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "reviewer": {"approved": True, "reason": "already reviewed", "risks": []},
                    }
                ],
            }
        )
        with (
            patch.object(repair, "enforce_decision_gate") as gate,
            patch.object(repair, "run_verification_commands") as verify,
            patch.object(repair, "invoke_cached") as invoke,
        ):
            result = repair.resume_repair_loop(session_id)
        self.assertEqual(result["status"], "approved")
        gate.assert_called_once_with("reviewer")
        verify.assert_not_called()
        invoke.assert_not_called()

    def test_final_reviewer_gate_closure_rolls_back_instead_of_approving(self) -> None:
        passed = {"passed": True, "results": []}
        reviewer_checks = 0

        def gate(role: str) -> None:
            nonlocal reviewer_checks
            if role == "reviewer":
                reviewer_checks += 1
                if reviewer_checks == 2:
                    raise RuntimeError("decision gate closed during review")

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            if role == "debugger":
                return {"content": json.dumps({"diagnosis": "bad", "files": [], "strategy": "fix"})}
            if role == "coder":
                return {"content": "```diff\n--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-a\n+b\n```"}
            if role == "reviewer":
                return {"content": json.dumps({"approved": True, "reason": "ok", "risks": []})}
            raise AssertionError(role)

        with (
            patch.object(repair, "enforce_decision_gate", side_effect=gate),
            patch.object(repair, "run_verification_commands", side_effect=[self.failed_verification(), passed]),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke),
            patch.object(repair, "apply_patch_text", return_value={"patch_id": "20260719T000000000099Z"}),
            patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback,
        ):
            session = repair.run_repair_loop("Fix stale decision", max_attempts=1)
        self.assertEqual(session["status"], "attempts_exhausted")
        self.assertNotEqual(session["attempts"][0]["status"], "approved")
        rollback.assert_called_once()

    def test_resume_does_not_finalize_saved_approval_after_gate_closes(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000106Z",
                "task": "resume stale approval",
                "status": "running",
                "max_attempts": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "reviewer": {"approved": True, "reason": "old approval", "risks": []},
                    }
                ],
            }
        )
        with patch.object(
            repair, "enforce_decision_gate", side_effect=RuntimeError("decision gate closed")
        ):
            with self.assertRaisesRegex(RuntimeError, "decision gate closed"):
                repair.resume_repair_loop(session_id)
        unchanged = repair.load_repair_session(session_id)
        self.assertEqual(unchanged["status"], "running")
        self.assertNotEqual(unchanged["attempts"][0]["status"], "approved")

    def test_resume_rolls_back_patch_when_saved_approval_becomes_stale(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000107Z",
                "task": "resume stale applied approval",
                "status": "running",
                "max_attempts": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "patch": {"patch_id": "20260719T000000000108Z"},
                        "reviewer": {"approved": True, "reason": "old approval", "risks": []},
                    }
                ],
            }
        )
        with (
            patch.object(repair, "enforce_decision_gate", side_effect=RuntimeError("decision gate closed")),
            patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback,
        ):
            with self.assertRaisesRegex(RuntimeError, "decision gate closed"):
                repair.resume_repair_loop(session_id)
        rollback.assert_called_once_with("20260719T000000000108Z")
        session = repair.load_repair_session(session_id)
        attempt = session["attempts"][0]
        self.assertEqual(attempt["status"], "stale_approval_rolled_back")
        self.assertTrue(attempt["rollback"]["rolled_back"])

    def test_resume_applies_saved_diff_without_repeating_generation(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000007Z",
                "task": "resume saved diff",
                "status": "running",
                "max_attempts": 1,
                "budget": {"elapsed_seconds": 1.0, "ai_calls": 2},
                "initial_verification": self.failed_verification(),
                "attempts": [{"attempt": 1, "status": "running"}],
            }
        )
        diff = "--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        diff_path = self.root / "workspace" / "repairs" / session_id / "attempt-1.diff"
        diff_path.write_text(diff, encoding="utf-8")

        def fake_invoke(role: str, prompt: str, **kwargs: object) -> dict[str, object]:
            self.assertEqual(role, "reviewer")
            return {"content": json.dumps({"approved": True, "reason": "passes", "risks": []})}

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "apply_patch_text", return_value={"patch_id": "20260719T000000000008Z"}) as apply,
            patch.object(repair, "run_verification_commands", return_value={"passed": True, "results": []}),
            patch.object(repair, "invoke_cached", side_effect=fake_invoke) as invoke,
        ):
            result = repair.resume_repair_loop(session_id)
        self.assertEqual(result["status"], "approved")
        apply.assert_called_once_with(diff)
        self.assertEqual(invoke.call_count, 1)

    def test_resume_rolls_back_when_saved_stage_processing_fails(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000009Z",
                "task": "resume malformed review",
                "status": "running",
                "max_attempts": 2,
                "budget": {"elapsed_seconds": 1.0, "ai_calls": 2},
                "initial_verification": self.failed_verification(),
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "patch": {"patch_id": "20260719T000000000010Z"},
                        "verification": {"passed": True, "results": []},
                    }
                ],
            }
        )
        diff_path = self.root / "workspace" / "repairs" / session_id / "attempt-1.diff"
        diff_path.write_text("--- a/src/sample.py\n+++ b/src/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n", encoding="utf-8")
        resumed = {
            "session_id": "20260719T000000000018Z",
            "status": "approved",
            "resumed_from": session_id,
        }

        def complete_successor(*args: object, **kwargs: object) -> dict[str, object]:
            time.sleep(0.002)
            resumed["started_at"] = repair._now()
            resumed["completed_at"] = repair._now()
            repair._save_session(str(resumed["session_id"]), resumed)
            return resumed

        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(repair, "patch_state", return_value={"state": "applied", "conflicts": []}),
            patch.object(repair, "invoke_cached", return_value={"content": json.dumps({"approved": "yes"})}),
            patch.object(repair, "rollback_patch", return_value={"rolled_back": True}) as rollback,
            patch.object(repair, "run_repair_loop", side_effect=complete_successor) as run_loop,
        ):
            result = repair.resume_repair_loop(session_id)
        self.assertEqual(result, resumed)
        rollback.assert_called_once_with("20260719T000000000010Z")
        run_loop.assert_called_once_with(
            "resume malformed review",
            max_attempts=1,
            retries=1,
            resumed_from=session_id,
        )
        original = repair.load_repair_session(session_id)
        self.assertEqual(original["status"], "superseded")
        self.assertEqual(original["successor_session_id"], resumed["session_id"])
        self.assertEqual(repair.load_repair_session("latest")["session_id"], resumed["session_id"])

    def test_resume_stops_when_rollback_conflicts(self) -> None:
        session_id = self.write_session(
            {
                "session_id": "20260719T000000000003Z",
                "task": "resume task",
                "status": "running",
                "max_attempts": 2,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "running",
                        "patch": {"patch_id": "20260719T000000000004Z"},
                    }
                ],
            }
        )
        with (
            patch.object(repair, "enforce_decision_gate"),
            patch.object(
                repair,
                "patch_state",
                return_value={"state": "conflict", "conflicts": ["src/sample.py"]},
            ),
            patch.object(repair, "rollback_patch") as rollback,
        ):
            with self.assertRaisesRegex(RuntimeError, "patch state conflict"):
                repair.resume_repair_loop(session_id)
        rollback.assert_not_called()
        saved = repair.load_repair_session(session_id)
        self.assertEqual(saved["status"], "rollback_blocked")


if __name__ == "__main__":
    unittest.main()
