from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app import project_docs
from haness_frame_app.templates.runtime.roles import ROLE_ORDER


class _GoldenAiHandler(BaseHTTPRequestHandler):
    claim_id = ""
    roles: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = request.get("messages", [])
        system = "\n".join(
            str(item.get("content", "")) for item in messages if item.get("role") == "system"
        )
        role = next((name for name in ROLE_ORDER if f"Role Packet: {name}" in system), "")
        type(self).roles.append(role)
        if role == "planner":
            content = "Adopt the smallest calculator correction and verify the public addition contract."
        elif role == "decision_maker":
            content = json.dumps(
                {
                    "decision": "Correct calculator addition with one bounded source change.",
                    "rationale": "The accepted claim and test evidence require addition semantics.",
                    "agreements": ["Preserve the public add function."],
                    "disagreements": ["Broader calculator features are out of scope."],
                    "risks": ["The declared regression test must pass."],
                    "confidence": "high",
                    "implementation_brief": ["Change subtraction to addition in src/calculator.py."],
                    "verification_commands": ["python -m unittest discover -s tests"],
                    "claim_ids": [type(self).claim_id],
                }
            )
        elif role == "debugger":
            content = json.dumps(
                {
                    "diagnosis": "add subtracts its second operand",
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
            content = json.dumps(
                {"approved": True, "reason": "The declared regression test passes.", "risks": []}
            )
        else:
            self.send_error(400, "unsupported golden-test role")
            return
        response = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class GoldenHarnessE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "golden-project"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _GoldenAiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _GoldenAiHandler.claim_id = ""
        _GoldenAiHandler.roles = []
        self.thread.start()
        with (
            patch.object(project_docs, "project_dir", return_value=self.project),
            patch.object(project_docs, "default_project_settings", return_value={"role_assignments": {}}),
            patch.object(
                project_docs,
                "project_service_snapshot",
                return_value={"role_services": {}, "fallback_service": {}},
            ),
        ):
            project_docs.create_project_files(
                "golden-project",
                "Build and verify a corrected calculator with local AI",
                "Build and verify a corrected calculator with local AI",
                False,
            )
        self._configure_project()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def write_json(self, relative: str, payload: object) -> None:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _configure_project(self) -> None:
        service = {
            "name": "golden-local-ai",
            "provider_type": "openai_compatible",
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
            "model": "golden-model",
            "enabled": True,
        }
        self.write_json(
            "workspace/services.json",
            {"role_services": {role: service for role in ROLE_ORDER}, "fallback_service": {}},
        )
        verification = "python -m unittest discover -s tests"
        self.write_json(
            "workspace/verification-policy.json",
            {"allowed_commands": [verification], "timeout_seconds": 20, "max_output_chars": 12000},
        )
        repair_policy = json.loads(
            (self.project / "workspace" / "repair-policy.json").read_text(encoding="utf-8")
        )
        repair_policy.update(
            {
                "max_attempts": 1,
                "reuse_ai_responses": False,
                "require_independent_reviewer_service": False,
            }
        )
        self.write_json("workspace/repair-policy.json", repair_policy)
        (self.project / "src" / "calculator.py").write_text(
            "def add(a, b):\n    return a - b\n", encoding="utf-8"
        )
        test_path = self.project / "tests" / "test_calculator.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(
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

    def add_evidence(self, url: str, title: str) -> None:
        self.run_app(
            "add-evidence",
            "--query",
            title,
            "--provider",
            "fixture",
            "--url",
            url,
            "--title",
            title,
            "--excerpt",
            "This detailed fixture supports calculator behavior and executable regression testing.",
            "--confidence",
            "high",
            "--why-it-matters",
            "It supports the bounded calculator correction.",
            "--recommended-use",
            "Use it in the accepted decision.",
        )

    def test_generated_project_completes_evidence_debate_repair_and_qualification(self) -> None:
        initial_gate = json.loads(self.run_app("gate", expected_code=1).stdout)
        self.assertFalse(initial_gate["allowed"])

        support_url = "https://example.com/calculator-contract"
        self.add_evidence(support_url, "Calculator contract")
        self.add_evidence("https://example.org/calculator-test", "Calculator regression test")
        claim = json.loads(
            self.run_app(
                "claim-add",
                "--claim",
                "The add function must return the arithmetic sum.",
                "--support-url",
                support_url,
                "--confidence",
                "high",
            ).stdout
        )
        _GoldenAiHandler.claim_id = str(claim["claim_id"])

        debate_report = json.loads(
            self.run_app(
                "debate-rounds",
                "--prompt",
                "Evaluate the bounded calculator correction using verified evidence",
                "--roles",
                "planner",
                "--rounds",
                "1",
                "--retries",
                "0",
            ).stdout
        )
        self.assertEqual(debate_report["verdict"]["claim_ids"], [_GoldenAiHandler.claim_id])
        self.run_app("decision-draft")
        gate = json.loads(self.run_app("gate").stdout)
        self.assertTrue(gate["allowed"], gate["issues"])

        repair = json.loads(
            self.run_app(
                "repair-run",
                "--task",
                "Fix calculator addition",
                "--max-attempts",
                "1",
                "--retries",
                "0",
            ).stdout
        )
        self.assertEqual(repair["status"], "approved")
        self.assertFalse(repair["initial_verification"]["passed"])
        self.assertTrue(repair["attempts"][0]["verification"]["passed"])
        self.assertIn("return a + b", (self.project / "src" / "calculator.py").read_text(encoding="utf-8"))

        qualification = json.loads(
            self.run_app("qualify", "--run-verification", expected_code=0).stdout
        )
        self.assertTrue(qualification["qualified"], qualification["issues"])
        self.assertEqual(qualification["execution_history"]["needs_attention"], 0)
        self.assertEqual(
            _GoldenAiHandler.roles,
            ["planner", "decision_maker", "debugger", "coder", "reviewer"],
        )


if __name__ == "__main__":
    unittest.main()
