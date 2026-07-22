from __future__ import annotations

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


class _PipelineAiHandler(BaseHTTPRequestHandler):
    roles: list[str] = []
    critic_failed = False

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = request.get("messages", [])
        system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        role = next((name for name in ("planner", "critic") if f"Role Packet: {name}" in system), "")
        self.roles.append(role)
        if role == "critic" and not type(self).critic_failed:
            type(self).critic_failed = True
            self.send_error(503, "temporary critic failure")
            return
        content = "Plan with explicit verification." if role == "planner" else "Critique confirms the verification gap."
        response = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class PipelineProcessE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PipelineAiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _PipelineAiHandler.roles = []
        _PipelineAiHandler.critic_failed = False
        self.thread.start()
        self._create_project()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: object) -> None:
        path = self.project / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _create_project(self) -> None:
        shutil.copytree(TEMPLATES / "runtime", self.project / "src" / "harness_app")
        shutil.copy2(TEMPLATES / "app.py", self.project / "app.py")
        service = {
            "name": "pipeline-fixture",
            "provider_type": "openai_compatible",
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
            "model": "fixture-model",
            "enabled": True,
        }
        self._write_json(
            "workspace/services.json",
            {"role_services": {role: service for role in ("planner", "critic")}, "fallback_service": {}},
        )
        self._write_json("workspace/scorecard.json", {"checks": {}})
        self._write_json(
            "workspace/orchestration-policy.json",
            {
                "max_roles": 4,
                "max_prompt_chars": 1000,
                "max_system_chars": 10000,
                "max_context_chars": 20000,
                "max_elapsed_seconds": 30,
                "max_ai_calls": 4,
            },
        )

    def run_app(self, *args: str, expected_code: int) -> subprocess.CompletedProcess[str]:
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

    def test_cli_pipeline_resumes_only_failed_role_and_is_idempotent(self) -> None:
        failed = self.run_app(
            "pipeline",
            "--roles",
            "planner,critic",
            "--prompt",
            "Build and challenge a plan",
            "--retries",
            "0",
            expected_code=1,
        )
        self.assertIn("HTTP Error 503", failed.stderr)
        status = json.loads(self.run_app("pipeline-status", "--id", "latest", expected_code=0).stdout)
        self.assertEqual(status["status"], "failed")
        self.assertEqual([item["role"] for item in status["results"]], ["planner"])
        self.assertEqual(status["budget"]["ai_calls"], 2)

        run_id = str(status["run_id"])
        resumed = self.run_app("pipeline-resume", "--id", run_id, expected_code=0)
        self.assertIn(f"run_id: {run_id}", resumed.stdout)
        completed = json.loads(self.run_app("pipeline-status", "--id", run_id, expected_code=0).stdout)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual([item["role"] for item in completed["results"]], ["planner", "critic"])
        self.assertEqual(completed["budget"]["ai_calls"], 3)
        self.assertIn("Previous role (planner) output", completed["results"][1]["system"])
        self.assertEqual(_PipelineAiHandler.roles, ["planner", "critic", "critic"])

        self.run_app("pipeline-resume", "--id", run_id, expected_code=0)
        self.assertEqual(_PipelineAiHandler.roles, ["planner", "critic", "critic"])

    def test_cli_can_abandon_failed_pipeline_without_another_provider_call(self) -> None:
        self.run_app(
            "pipeline",
            "--roles",
            "planner,critic",
            "--prompt",
            "An obsolete planning run",
            "--retries",
            "0",
            expected_code=1,
        )
        failed = json.loads(self.run_app("pipeline-status", "--id", "latest", expected_code=0).stdout)
        run_id = str(failed["run_id"])
        abandoned = json.loads(
            self.run_app(
                "pipeline-abandon",
                "--id",
                run_id,
                "--reason",
                "Superseded by corrected requirements",
                expected_code=0,
            ).stdout
        )
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["abandonment_reason"], "Superseded by corrected requirements")
        resume = self.run_app("pipeline-resume", "--id", run_id, expected_code=1)
        self.assertIn("terminal: abandoned", resume.stderr)
        self.assertEqual(_PipelineAiHandler.roles, ["planner", "critic"])


if __name__ == "__main__":
    unittest.main()
