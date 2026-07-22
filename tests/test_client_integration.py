from __future__ import annotations

import json
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

from haness_frame_app.templates.runtime import audit, client, engine, storage


class _MockAiHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.requests.append({"path": self.path, "payload": payload})
        if self.path == "/primary/chat/completions":
            self.send_response(503)
            self.end_headers()
            return
        if self.path == "/malformed/chat/completions":
            response = {"choices": []}
        elif self.path == "/api/chat":
            response = {"message": {"content": "Ollama response"}}
        else:
            response = {"choices": [{"message": {"content": "<think>hidden</think>Visible response"}}]}
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ClientIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        (self.root / "workspace" / "evidence-policy.json").write_text("{}", encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockAiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _MockAiHandler.requests = []
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(engine, "ROOT", self.root),
            patch.object(engine, "STATE_FILE", self.root / "workspace" / "state.json"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def service(self, provider: str, path: str, name: str) -> dict[str, object]:
        return {
            "name": name,
            "provider_type": provider,
            "base_url": f"{self.base_url}{path}",
            "model": "mock-model",
            "enabled": True,
        }

    def write_services(self, role_service: dict[str, object], fallback: dict[str, object] | None = None) -> None:
        payload = {"role_services": {"planner": role_service}, "fallback_service": fallback or {}}
        (self.root / "workspace" / "services.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_openai_compatible_request_and_response_contract(self) -> None:
        self.write_services(self.service("openai_compatible", "/v1", "primary"))
        result = client.invoke("planner", "Plan this", temperature=0.1, max_tokens=123, retries=0)
        self.assertEqual(result["content"], "Visible response")
        request = _MockAiHandler.requests[0]
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertEqual(request["payload"]["model"], "mock-model")
        self.assertEqual(request["payload"]["max_tokens"], 123)
        self.assertFalse(result["diagnostics"]["used_fallback"])
        self.assertEqual(result["diagnostics"]["attempts"][0]["outcome"], "success")
        report = client.invocation_report({
            **result,
            "raw": {"secret": "not exported"},
            "service": {**result["service"], "base_url": "http://user:secret@127.0.0.1:1234/v1?token=secret"},
        })
        self.assertNotIn("raw", report)
        self.assertEqual(report["service"]["name"], "primary")
        self.assertEqual(report["service"]["base_url"], "http://127.0.0.1:1234/v1")

    def test_service_request_timeout_is_forwarded_to_http_client(self) -> None:
        service = {**self.service("openai_compatible", "/v1", "primary"), "request_timeout_seconds": 45}
        self.write_services(service)
        with patch.object(client.urllib.request, "urlopen", wraps=client.urllib.request.urlopen) as urlopen:
            result = client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(result["content"], "Visible response")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 45)

    def test_ollama_request_and_response_contract(self) -> None:
        self.write_services(self.service("ollama", "", "ollama"))
        result = client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(result["content"], "Ollama response")
        request = _MockAiHandler.requests[0]
        self.assertEqual(request["path"], "/api/chat")
        self.assertFalse(request["payload"]["stream"])

    def test_retryable_primary_failure_uses_distinct_fallback(self) -> None:
        primary = self.service("openai_compatible", "/primary", "primary")
        fallback = self.service("openai_compatible", "/fallback", "fallback")
        self.write_services(primary, fallback)
        result = client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(result["content"], "Visible response")
        self.assertIn("503", result["primary_error"])
        self.assertEqual([item["path"] for item in _MockAiHandler.requests], [
            "/primary/chat/completions",
            "/fallback/chat/completions",
        ])
        diagnostics = result["diagnostics"]
        self.assertTrue(diagnostics["used_fallback"])
        self.assertEqual(diagnostics["fallback_reason"]["error_category"], "http_server")
        self.assertEqual([item["route"] for item in diagnostics["attempts"]], ["primary", "fallback"])

    def test_equivalent_alias_fallback_is_not_retried(self) -> None:
        primary = self.service("openai", "/primary/", "primary")
        fallback = {**primary, "name": "fallback-alias", "provider_type": "vllm"}
        self.write_services(primary, fallback)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        self.assertEqual([item["path"] for item in _MockAiHandler.requests], ["/primary/chat/completions"])
        self.assertFalse(raised.exception.diagnostics["used_fallback"])

    def test_malformed_success_response_uses_fallback(self) -> None:
        primary = self.service("openai_compatible", "/malformed", "malformed")
        fallback = self.service("openai_compatible", "/fallback", "fallback")
        self.write_services(primary, fallback)
        result = client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(result["content"], "Visible response")
        self.assertIn("non-empty choices", result["primary_error"])
        self.assertEqual(result["diagnostics"]["fallback_reason"]["error_category"], "response_contract")

    def test_total_failure_exposes_structured_attempt_history(self) -> None:
        primary = self.service("openai_compatible", "/primary", "primary")
        fallback = self.service("openai_compatible", "/primary", "fallback")
        fallback["model"] = "fallback-model"
        self.write_services(primary, fallback)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=1)
        diagnostics = raised.exception.diagnostics
        self.assertEqual(len(diagnostics["attempts"]), 4)
        self.assertEqual([item["route"] for item in diagnostics["attempts"]], [
            "primary", "primary", "fallback", "fallback",
        ])
        self.assertTrue(all(item["error_category"] == "http_server" for item in diagnostics["attempts"]))
        self.assertEqual(diagnostics["final_error"]["http_status"], 503)

    def test_non_retryable_configuration_failure_is_structured(self) -> None:
        service = self.service("unsupported", "/unused", "unsupported")
        self.write_services(service)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["final_error"]["error_category"], "configuration")
        self.assertFalse(diagnostics["final_error"]["retryable"])

    def test_disabled_primary_is_blocked_before_network_call(self) -> None:
        service = {**self.service("openai_compatible", "/v1", "disabled"), "enabled": False}
        self.write_services(service)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(_MockAiHandler.requests, [])
        self.assertEqual(raised.exception.diagnostics["final_error"]["error_category"], "configuration")

    def test_credentialed_base_url_is_blocked_without_secret_echo(self) -> None:
        service = self.service("openai_compatible", "/v1", "unsafe")
        service["base_url"] = "http://user:very-secret@127.0.0.1:invalid/v1?token=also-secret"
        self.write_services(service)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        exported = json.dumps(raised.exception.diagnostics)
        self.assertNotIn("very-secret", exported)
        self.assertNotIn("also-secret", exported)
        self.assertEqual(_MockAiHandler.requests, [])

    def test_invalid_fallback_is_reported_without_attempting_it(self) -> None:
        primary = self.service("openai_compatible", "/primary", "primary")
        fallback = {**self.service("openai_compatible", "/fallback", "fallback"), "enabled": False}
        self.write_services(primary, fallback)
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        self.assertEqual([item["path"] for item in _MockAiHandler.requests], ["/primary/chat/completions"])
        self.assertIn("service is disabled", raised.exception.diagnostics["fallback_configuration"])

    def test_missing_role_service_is_structured(self) -> None:
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {}, "fallback_service": {}}),
            encoding="utf-8",
        )
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["attempts"], [])
        self.assertEqual(diagnostics["final_error"]["error_category"], "configuration")

    def test_malformed_services_json_is_structured_without_network_call(self) -> None:
        (self.root / "workspace" / "services.json").write_text('{"role_services":', encoding="utf-8")
        with self.assertRaises(client.RoleInvocationError) as raised:
            client.invoke("planner", "Plan this", retries=0)
        self.assertEqual(_MockAiHandler.requests, [])
        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["attempts"], [])
        self.assertEqual(diagnostics["final_error"]["error_category"], "configuration")
        self.assertIn("invalid JSON", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
