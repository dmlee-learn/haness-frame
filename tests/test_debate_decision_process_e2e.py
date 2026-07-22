from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "haness_frame_app" / "templates"


class _DebateAiHandler(BaseHTTPRequestHandler):
    roles: list[str] = []
    fail_judge_once = False

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = request.get("messages", [])
        system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        role = next((name for name in ("planner", "decision_maker") if f"Role Packet: {name}" in system), "")
        self.roles.append(role)
        if role == "planner":
            content = "Adopt the bounded worker and verify its public contract with the approved test command."
        elif role == "decision_maker":
            if type(self).fail_judge_once:
                type(self).fail_judge_once = False
                self.send_error(503, "temporary judge failure")
                return
            content = json.dumps(
                {
                    "decision": "Adopt the bounded worker design.",
                    "rationale": "The evidence and accepted claim support bounded execution.",
                    "agreements": ["Preserve the public interface."],
                    "disagreements": ["Queue storage remains outside this change."],
                    "risks": ["Rollback coverage must remain executable."],
                    "confidence": "high",
                    "implementation_brief": ["Implement the worker behind the existing public interface."],
                    "verification_commands": ["python -m compileall src"],
                    "claim_ids": ["claim-bounded-worker"],
                }
            )
        else:
            self.send_error(400, "unknown role")
            return
        response = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class DebateDecisionProcessE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _DebateAiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _DebateAiHandler.roles = []
        _DebateAiHandler.fail_judge_once = False
        self.thread.start()
        self._create_project()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def write_json(self, rel_path: str, payload: object) -> None:
        path = self.project / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _create_project(self) -> None:
        shutil.copytree(TEMPLATES / "runtime", self.project / "src" / "harness_app")
        shutil.copy2(TEMPLATES / "app.py", self.project / "app.py")
        (self.project / "context").mkdir()
        (self.project / "context" / "business-context.md").write_text(
            "Working description:\n\n```text\nBuild a bounded worker\n```\n", encoding="utf-8"
        )
        retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
        urls = ["https://example.com/worker", "https://example.org/verification"]
        records = [
            {
                "query": f"worker evidence {index}",
                "provider": "fixture",
                "url": url,
                "title": f"Worker evidence {index}",
                "excerpt": "A detailed fixture excerpt supports bounded worker verification.",
                "retrieved_at": retrieved_at,
                "confidence": "high",
                "why_it_matters": "It supports the accepted worker design.",
                "recommended_use": "Use it in the decision record.",
            }
            for index, url in enumerate(urls, start=1)
        ]
        self.write_json("workspace/evidence/search-evidence.json", records)
        self.write_json(
            "workspace/evidence/claim-evidence.json",
            [
                {
                    "claim_id": "claim-bounded-worker",
                    "claim": "The bounded worker preserves the public execution contract.",
                    "status": "accepted",
                    "confidence": "high",
                    "supporting_urls": [urls[0]],
                    "challenging_urls": [],
                    "resolution": "",
                }
            ],
        )
        self.write_json(
            "workspace/evidence-policy.json",
            {
                "min_records": 2,
                "min_distinct_urls": 2,
                "allowed_confidence": ["high", "medium"],
                "min_excerpt_chars": 20,
                "require_claim_matrix": True,
                "require_decision_snapshot": True,
                "min_claims": 1,
                "min_supporting_sources_per_claim": 1,
                "require_challenge_resolution": True,
                "allowed_claim_confidence": ["high", "medium"],
            },
        )
        self.write_json(
            "workspace/orchestration-policy.json",
            {
                "max_roles": 4,
                "max_prompt_chars": 2000,
                "max_system_chars": 20000,
                "max_context_chars": 30000,
                "min_output_chars": 20,
                "max_output_chars": 10000,
                "max_elapsed_seconds": 30,
                "max_ai_calls": 4,
            },
        )
        self.write_json("workspace/scorecard.json", {"checks": {}})
        service = {
            "name": "debate-fixture",
            "provider_type": "openai_compatible",
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
            "model": "fixture-model",
            "enabled": True,
        }
        self.write_json(
            "workspace/services.json",
            {"role_services": {role: service for role in ("planner", "decision_maker")}, "fallback_service": {}},
        )

    def run_app(self, *args: str, expected_code: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, "app.py", *args],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, expected_code, completed.stderr)
        return completed

    def test_debate_verdict_opens_decision_gate_and_stales_after_evidence_change(self) -> None:
        prompt = "Evaluate the bounded worker using verified project knowledge"
        report = json.loads(
            self.run_app(
                "debate-rounds", "--prompt", prompt, "--roles", "planner", "--rounds", "1", "--retries", "0"
            ).stdout
        )
        self.assertEqual(report["verdict"]["claim_ids"], ["claim-bounded-worker"])
        self.assertTrue(str(report["verdict_sha256"]))
        self.assertTrue(str(report["evidence_input_digest"]).startswith("sha256:"))
        self.run_app("decision-draft")
        gate = json.loads(self.run_app("gate").stdout)
        self.assertTrue(gate["allowed"], gate["issues"])
        decision_text = (self.project / "docs" / "03-decision-record.md").read_text(encoding="utf-8")
        self.assertIn("Adopt the bounded worker design.", decision_text)
        self.assertIn("claim-bounded-worker", decision_text)
        self.assertEqual(_DebateAiHandler.roles, ["planner", "decision_maker"])
        audit_text = (self.project / "workspace" / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(prompt, audit_text)

        evidence_path = self.project / "workspace" / "evidence" / "search-evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence[0]["excerpt"] += " Updated after debate."
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        stale = self.run_app("decision-draft", expected_code=1)
        self.assertIn("evidence snapshot is stale", stale.stderr)

    def test_cli_resumes_failed_judge_without_repeating_round(self) -> None:
        _DebateAiHandler.fail_judge_once = True
        failed = self.run_app(
            "debate-rounds",
            "--prompt",
            "Choose the bounded worker",
            "--roles",
            "planner",
            "--rounds",
            "1",
            "--retries",
            "0",
            expected_code=1,
        )
        self.assertIn("HTTP Error 503", failed.stderr)
        session = json.loads(self.run_app("debate-status", "--id", "latest").stdout)
        self.assertEqual(session["status"], "failed")
        self.assertEqual(session["stage"], "judge")
        self.assertEqual(len(session["round_results"]), 1)
        session_id = str(session["session_id"])

        report = json.loads(self.run_app("debate-resume", "--id", session_id).stdout)
        self.assertEqual(report["verdict"]["decision"], "Adopt the bounded worker design.")
        self.assertEqual(_DebateAiHandler.roles, ["planner", "decision_maker", "decision_maker"])
        completed = json.loads(self.run_app("debate-status", "--id", session_id).stdout)
        self.assertEqual(completed["status"], "completed")

        self.run_app("debate-resume", "--id", session_id)
        self.assertEqual(_DebateAiHandler.roles, ["planner", "decision_maker", "decision_maker"])

    def test_cli_abandons_failed_debate_without_another_provider_call(self) -> None:
        _DebateAiHandler.fail_judge_once = True
        self.run_app(
            "debate-rounds",
            "--prompt",
            "Choose the bounded worker",
            "--roles",
            "planner",
            "--rounds",
            "1",
            "--retries",
            "0",
            expected_code=1,
        )
        session = json.loads(self.run_app("debate-status", "--id", "latest").stdout)
        calls_before = list(_DebateAiHandler.roles)
        abandoned = json.loads(
            self.run_app(
                "debate-abandon",
                "--id",
                str(session["session_id"]),
                "--reason",
                "Superseded by corrected requirements",
            ).stdout
        )
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(_DebateAiHandler.roles, calls_before)
        resume = self.run_app("debate-resume", "--id", str(session["session_id"]), expected_code=1)
        self.assertIn("terminal: abandoned", resume.stderr)


if __name__ == "__main__":
    unittest.main()
