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


class _RepairAiHandler(BaseHTTPRequestHandler):
    roles: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = request.get("messages", [])
        system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        role = next((name for name in ("debugger", "coder", "reviewer") if f"Role Packet: {name}" in system), "")
        self.roles.append(role)
        if role == "debugger":
            content = json.dumps(
                {
                    "diagnosis": "add subtracts the second operand",
                    "files": ["src/calculator.py"],
                    "strategy": "replace subtraction with addition",
                }
            )
        elif role == "coder":
            content = """```diff
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
```"""
        elif role == "reviewer":
            content = json.dumps({"approved": True, "reason": "the declared tests pass", "risks": []})
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


class RepairProcessE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RepairAiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _RepairAiHandler.roles = []
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
        runtime = self.project / "src" / "harness_app"
        shutil.copytree(TEMPLATES / "runtime", runtime)
        shutil.copy2(TEMPLATES / "app.py", self.project / "app.py")
        (self.project / "src" / "calculator.py").write_text(
            "def add(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        test_file = self.project / "tests" / "test_calculator.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            """import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from calculator import add


class CalculatorTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
""",
            encoding="utf-8",
        )
        command = "python -m unittest discover -s tests"
        decision = f"""# Decision

## Accepted Decision

Fix calculator addition with the smallest source change.

## Evidence Used

- https://example.com/addition
- https://example.org/testing

## Implementation Brief For Coder

Change only `src/calculator.py` and preserve the public function.

## Verification Commands

- `{command}`
"""
        decision_path = self.project / "docs" / "03-decision-record.md"
        decision_path.parent.mkdir(parents=True)
        decision_path.write_text(decision, encoding="utf-8")
        retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
        records = []
        for index, url in enumerate(("https://example.com/addition", "https://example.org/testing"), start=1):
            records.append(
                {
                    "query": f"evidence {index}",
                    "provider": "fixture",
                    "url": url,
                    "title": f"Evidence {index}",
                    "excerpt": "A sufficiently detailed evidence excerpt for the process test.",
                    "retrieved_at": retrieved_at,
                    "confidence": "high",
                    "why_it_matters": "It supports the accepted change.",
                    "recommended_use": "Use it to validate the implementation.",
                }
            )
        self._write_json("workspace/evidence/search-evidence.json", records)
        self._write_json(
            "workspace/evidence-policy.json",
            {
                "min_records": 2,
                "min_distinct_urls": 2,
                "allowed_confidence": ["high", "medium"],
                "max_age_days": 3650,
                "max_future_skew_minutes": 10,
                "min_excerpt_chars": 20,
                "min_search_coverage_ratio": 0.0,
            },
        )
        self._write_json("workspace/verification-policy.json", {"allowed_commands": [command], "timeout_seconds": 20, "max_output_chars": 12000})
        self._write_json(
            "workspace/repair-policy.json",
            {
                "editable_roots": ["src", "tests"],
                "max_patch_files": 2,
                "max_patch_bytes": 10000,
                "max_attempts": 1,
                "rollback_on_failure": True,
                "max_context_files": 2,
                "max_context_chars": 10000,
                "reuse_ai_responses": False,
                "ai_cache_max_age_seconds": 3600,
            },
        )
        service = {
            "name": "mock-repair-ai",
            "provider_type": "openai_compatible",
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
            "model": "mock-model",
            "enabled": True,
        }
        self._write_json(
            "workspace/services.json",
            {"role_services": {role: service for role in ("debugger", "coder", "reviewer")}, "fallback_service": {}},
        )
        self._write_json("workspace/scorecard.json", {"checks": {}})

    def test_cli_repairs_failed_code_and_records_independent_approval(self) -> None:
        completed = subprocess.run(
            [sys.executable, "app.py", "repair-run", "--task", "Fix calculator addition", "--max-attempts", "1", "--retries", "0"],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        session = json.loads(completed.stdout)
        self.assertEqual(session["status"], "approved", json.dumps(session, indent=2))
        self.assertFalse(session["initial_verification"]["passed"])
        self.assertTrue(session["attempts"][0]["verification"]["passed"])
        self.assertEqual(session["attempts"][0]["reviewer"]["approved"], True)
        self.assertEqual(_RepairAiHandler.roles, ["debugger", "coder", "reviewer"])
        self.assertIn("return a + b", (self.project / "src" / "calculator.py").read_text(encoding="utf-8"))
        self.assertTrue((self.project / "workspace" / "repairs" / "latest.json").is_file())
        self.assertTrue(any((self.project / "workspace" / "patches").iterdir()))

    def test_invoke_json_exposes_redacted_attempt_diagnostics(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "app.py",
                "invoke",
                "--role",
                "debugger",
                "--prompt",
                "Diagnose the calculator",
                "--retries",
                "0",
                "--json",
            ],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertNotIn("raw", report)
        self.assertEqual(report["diagnostics"]["attempts"][0]["outcome"], "success")
        self.assertEqual(report["diagnostics"]["attempts"][0]["route"], "primary")

    def test_role_plan_preserves_korean_task_through_cli(self) -> None:
        task = "보안 API 오류를 조사하고 수정한 뒤 회귀 테스트를 추가"
        completed = subprocess.run(
            [sys.executable, "app.py", "role-plan", "--task", task],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan["task"], task)
        self.assertEqual(
            plan["task_tags"],
            ["research", "bugfix", "architecture", "implementation", "high_risk"],
        )

    def test_cli_resumes_after_patch_with_reviewer_only(self) -> None:
        diff = """--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
        diff_path = self.project / "workspace" / "resume.diff"
        diff_path.write_text(diff, encoding="utf-8")
        applied = subprocess.run(
            [sys.executable, "app.py", "patch-apply", "--file", "workspace/resume.diff"],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        patch_metadata = json.loads(applied.stdout)
        session_id = "20260719T000000000011Z"
        session = {
            "session_id": session_id,
            "task": "Fix calculator addition",
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "completed_at": "",
            "status": "running",
            "max_attempts": 1,
            "budget": {"elapsed_seconds": 1.0, "ai_calls": 2},
            "initial_verification": {
                "passed": False,
                "results": [{"command": "python -m unittest discover -s tests", "passed": False}],
            },
            "attempts": [
                {
                    "attempt": 1,
                    "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "status": "running",
                    "diff_file": f"workspace/repairs/{session_id}/attempt-1.diff",
                    "patch": patch_metadata,
                }
            ],
        }
        session_dir = self.project / "workspace" / "repairs" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "attempt-1.diff").write_text(diff, encoding="utf-8")
        (session_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
        (self.project / "workspace" / "repairs" / "latest.json").write_text(json.dumps(session), encoding="utf-8")
        _RepairAiHandler.roles = []

        completed = subprocess.run(
            [sys.executable, "app.py", "repair-resume", "--id", session_id, "--retries", "0"],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        resumed = json.loads(completed.stdout)
        self.assertEqual(resumed["status"], "approved", json.dumps(resumed, indent=2))
        self.assertTrue(resumed["attempts"][0]["verification"]["passed"])
        self.assertEqual(_RepairAiHandler.roles, ["reviewer"])

    def test_cli_resume_returns_two_for_exhausted_durable_session(self) -> None:
        session_id = "20260719T000000000012Z"
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        session = {
            "session_id": session_id,
            "task": "Unresolved repair",
            "started_at": now,
            "completed_at": now,
            "status": "attempts_exhausted",
            "max_attempts": 1,
            "budget": {"elapsed_seconds": 1.0, "ai_calls": 2},
            "attempts": [],
        }
        session_dir = self.project / "workspace" / "repairs" / session_id
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
        (self.project / "workspace" / "repairs" / "latest.json").write_text(
            json.dumps(session), encoding="utf-8"
        )
        completed = subprocess.run(
            [sys.executable, "app.py", "repair-resume", "--id", session_id, "--retries", "0"],
            cwd=self.project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "attempts_exhausted")


if __name__ == "__main__":
    unittest.main()
