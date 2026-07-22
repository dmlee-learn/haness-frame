from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, diagnostics, storage


class _Response:
    status = 200

    def __init__(self, payload: object | None = None) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        if self.payload is None:
            return b""
        return json.dumps(self.payload).encode("utf-8")[:limit]


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.service = {
            "name": "local-ai",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:9000/v1",
            "model": "test-model",
            "api_key_env": "",
            "enabled": True,
        }
        self.write_services({"planner": self.service, "coder": dict(self.service)})
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

    def write_services(self, roles: dict[str, object]) -> None:
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": roles}),
            encoding="utf-8",
        )

    def test_config_check_groups_shared_service_without_probe(self) -> None:
        report = diagnostics.check_services(probe=False)
        self.assertTrue(report["valid"])
        self.assertEqual(report["service_count"], 1)
        self.assertEqual(report["services"][0]["roles"], ["coder", "planner"])

    def test_project_role_contract_reports_missing_service_keys(self) -> None:
        (self.root / "workspace" / "state.json").write_text(
            json.dumps({"default_roles": ["planner", "coder", "reviewer"]}), encoding="utf-8"
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertEqual(report["expected_roles"], ["coder", "planner", "reviewer"])
        self.assertEqual(report["unassigned_roles"], ["reviewer"])

    def test_service_assignment_snapshot_also_defines_required_roles(self) -> None:
        (self.root / "workspace" / "services.json").write_text(
            json.dumps(
                {
                    "role_service_assignments": {"planner": "local-ai", "critic": "local-ai"},
                    "role_services": {"planner": self.service},
                }
            ),
            encoding="utf-8",
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertEqual(report["unassigned_roles"], ["critic"])

    def test_assignment_map_must_match_configured_service_name(self) -> None:
        (self.root / "workspace" / "services.json").write_text(
            json.dumps(
                {
                    "role_service_assignments": {"planner": "expected-service"},
                    "role_services": {"planner": self.service},
                }
            ),
            encoding="utf-8",
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertIn("service assignment mismatch for role planner", report["configuration_issues"])

    def test_state_and_service_assignment_snapshots_must_agree(self) -> None:
        (self.root / "workspace" / "state.json").write_text(
            json.dumps({"role_assignments": {"planner": "old-service"}}), encoding="utf-8"
        )
        (self.root / "workspace" / "services.json").write_text(
            json.dumps(
                {
                    "role_service_assignments": {"planner": "local-ai"},
                    "role_services": {"planner": self.service},
                }
            ),
            encoding="utf-8",
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertIn("state and service assignment snapshots disagree for role planner", report["configuration_issues"])

    def test_corrupt_state_snapshot_is_not_ignored_or_overwritten(self) -> None:
        state_path = self.root / "workspace" / "state.json"
        original = '{"default_roles":["planner"],}'
        state_path.write_text(original, encoding="utf-8")
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertTrue(any("state.json contains invalid JSON" in issue for issue in report["configuration_issues"]))
        self.assertEqual(state_path.read_text(encoding="utf-8"), original)

    def test_assignment_map_shape_is_validated(self) -> None:
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_service_assignments": [], "role_services": {"planner": self.service}}),
            encoding="utf-8",
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertIn("role_service_assignments must be a JSON object", report["configuration_issues"][0])

    def test_shared_coder_and_reviewer_model_is_reported_as_warning(self) -> None:
        reviewer = dict(self.service)
        reviewer["name"] = "review-alias"
        self.write_services({"coder": self.service, "reviewer": reviewer})
        report = diagnostics.check_services(probe=False)
        self.assertTrue(report["valid"])
        self.assertFalse(report["review_independence"]["independent_service"])
        self.assertIn("same provider endpoint and model", report["warnings"][0])

    def test_distinct_reviewer_model_is_independent(self) -> None:
        reviewer = dict(self.service)
        reviewer["model"] = "review-model"
        self.write_services({"coder": self.service, "reviewer": reviewer})
        report = diagnostics.check_services(probe=False)
        self.assertTrue(report["review_independence"]["independent_service"])
        self.assertEqual(report["warnings"], [])

    def test_openai_alias_and_equivalent_url_do_not_bypass_independence(self) -> None:
        coder = {
            **self.service,
            "provider_type": "openai_compatible",
            "base_url": "HTTP://LOCALHOST:80/v1/",
        }
        reviewer = {
            **self.service,
            "name": "review-alias",
            "provider_type": "openai",
            "base_url": "http://localhost/v1",
        }
        self.write_services({"coder": coder, "reviewer": reviewer})
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["review_independence"]["independent_service"])
        self.assertIn("same provider endpoint and model", report["warnings"][0])

    def test_shared_debate_judge_model_is_reported_as_warning(self) -> None:
        judge = dict(self.service)
        judge["name"] = "judge-alias"
        self.write_services({"planner": self.service, "decision_maker": judge})
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["debate_judge_independence"]["independent_service"])
        self.assertIn("decision-maker judge shares", report["warnings"][0])
        self.assertEqual(report["debate_judge_independence"]["shared_roles"], ["planner"])

    def test_probe_calls_shared_endpoint_once(self) -> None:
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=_Response()) as urlopen:
            report = diagnostics.check_services(probe=True)
        self.assertTrue(report["valid"])
        urlopen.assert_called_once()

    def test_probe_groups_aliases_and_fallback_on_same_execution_route(self) -> None:
        planner = {
            **self.service,
            "provider_type": "openai",
            "base_url": "HTTP://LOCALHOST:80/v1/",
            "name": "planner-route",
        }
        fallback = {
            **self.service,
            "provider_type": "vllm",
            "base_url": "http://localhost/v1",
            "name": "fallback-alias",
        }
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"planner": planner}, "fallback_service": fallback}),
            encoding="utf-8",
        )
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=_Response()) as urlopen:
            report = diagnostics.check_services(probe=True)
        self.assertTrue(report["valid"])
        self.assertEqual(report["service_count"], 1)
        self.assertEqual(report["services"][0]["roles"], ["(fallback)", "planner"])
        urlopen.assert_called_once()

    def test_probe_failure_is_reported(self) -> None:
        error = urllib.error.URLError("offline")
        with patch.object(diagnostics.urllib.request, "urlopen", side_effect=error):
            report = diagnostics.check_services(probe=True)
        self.assertFalse(report["valid"])
        self.assertIn("endpoint probe failed", report["services"][0]["issues"][0])

    def test_openai_probe_rejects_missing_configured_model(self) -> None:
        response = _Response({"object": "list", "data": [{"id": "another-model"}]})
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=response):
            report = diagnostics.check_services(probe=True)
        self.assertFalse(report["valid"])
        self.assertIn("configured model is not listed: test-model", report["services"][0]["probe_detail"])

    def test_openai_probe_accepts_configured_model(self) -> None:
        response = _Response({"object": "list", "data": [{"id": "test-model"}]})
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=response):
            report = diagnostics.check_services(probe=True)
        self.assertTrue(report["valid"])
        self.assertIn("configured model is available", report["services"][0]["probe_detail"])

    def test_ollama_probe_accepts_implicit_latest_tag(self) -> None:
        service = dict(self.service)
        service.update({"provider_type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "test-model"})
        self.write_services({"planner": service})
        response = _Response({"models": [{"name": "test-model:latest"}]})
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=response):
            report = diagnostics.check_services(probe=True)
        self.assertTrue(report["valid"])

    def test_unrecognized_model_list_keeps_connectivity_result(self) -> None:
        response = _Response({"custom_models": ["test-model"]})
        with patch.object(diagnostics.urllib.request, "urlopen", return_value=response):
            report = diagnostics.check_services(probe=True)
        self.assertTrue(report["valid"])
        self.assertIn("format not recognized", report["services"][0]["probe_detail"])

    def test_no_probe_rejects_unsafe_or_malformed_base_urls(self) -> None:
        invalid_urls = [
            "ftp://example.com/v1",
            "http:///v1",
            "http://user:secret@example.com/v1",
            "https://example.com/v1?token=secret",
            "http://example.com:invalid/v1",
        ]
        for base_url in invalid_urls:
            with self.subTest(base_url=base_url):
                service = {**self.service, "base_url": base_url}
                self.write_services({"planner": service})
                report = diagnostics.check_services(probe=False)
                self.assertFalse(report["valid"])
                self.assertTrue(report["services"][0]["issues"])

    def test_configured_fallback_is_included_in_diagnostics(self) -> None:
        fallback = {**self.service, "name": "fallback", "enabled": False}
        (self.root / "workspace" / "services.json").write_text(
            json.dumps({"role_services": {"planner": self.service}, "fallback_service": fallback}),
            encoding="utf-8",
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        fallback_report = next(item for item in report["services"] if "(fallback)" in item["roles"])
        self.assertIn("service is disabled", fallback_report["issues"])

    def test_malformed_services_json_reports_location_without_content(self) -> None:
        secret = "very-secret-value"
        (self.root / "workspace" / "services.json").write_text(
            '{"role_services": ["' + secret + '",}', encoding="utf-8"
        )
        report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        issue = report["configuration_issues"][0]
        self.assertIn("invalid JSON at line", issue)
        self.assertNotIn(secret, issue)

    def test_invalid_services_schema_is_reported_explicitly(self) -> None:
        for payload, expected in [
            ([], "root must be a JSON object"),
            ({"role_services": []}, "role_services must be a JSON object"),
            ({"role_services": {}, "fallback_service": []}, "assign at least one role"),
        ]:
            with self.subTest(payload=payload):
                (self.root / "workspace" / "services.json").write_text(json.dumps(payload), encoding="utf-8")
                report = diagnostics.check_services(probe=False)
                self.assertFalse(report["valid"])
                self.assertTrue(any(expected in issue for issue in report["configuration_issues"]))

    def test_missing_api_key_environment_variable_is_reported_without_probe(self) -> None:
        service = dict(self.service)
        service["api_key_env"] = "HANESS_TEST_MISSING_KEY"
        self.write_services({"planner": service})
        with patch.dict("os.environ", {}, clear=True):
            report = diagnostics.check_services(probe=False)
        self.assertFalse(report["valid"])
        self.assertIn("HANESS_TEST_MISSING_KEY", report["services"][0]["issues"][0])

    def test_live_check_redacts_successful_response_content(self) -> None:
        service_report = {"valid": True, "services": [{"name": "local-ai"}]}
        invocation = {
            "content": "READY",
            "provider_type": "openai_compatible",
            "diagnostics": {
                "selected_service": {"name": "local-ai", "model": "test-model"},
                "used_fallback": False,
                "attempts": [{"outcome": "success"}],
            },
        }
        with (
            patch.object(diagnostics, "check_services", return_value=service_report),
            patch.object(diagnostics, "invoke", return_value=invocation) as invoke,
        ):
            report = diagnostics.live_check(role="planner")
        self.assertTrue(report["valid"])
        self.assertEqual(report["invocation"]["content_length"], 5)
        self.assertEqual(
            report["invocation"]["content_sha256"],
            "c2e3ac47f4a325469c1a2d5f117e463ec943c721986d5d9f09ac4540b7d80526",
        )
        self.assertNotIn("READY", json.dumps(report))
        self.assertEqual(invoke.call_args.kwargs["max_tokens"], 32)
        self.assertEqual(invoke.call_args.kwargs["retries"], 0)

    def test_live_check_does_not_invoke_when_probe_fails(self) -> None:
        service_report = {"valid": False, "services": [], "configuration_issues": ["offline"]}
        with (
            patch.object(diagnostics, "check_services", return_value=service_report),
            patch.object(diagnostics, "invoke") as invoke,
        ):
            report = diagnostics.live_check(role="planner")
        self.assertFalse(report["valid"])
        self.assertFalse(report["invocation"]["attempted"])
        invoke.assert_not_called()

    def test_live_check_returns_redacted_invocation_failure(self) -> None:
        failure = diagnostics.RoleInvocationError(
            "provider unavailable",
            {"role": "planner", "attempts": [], "final_error": {"error_category": "connection"}},
        )
        with (
            patch.object(diagnostics, "check_services", return_value={"valid": True, "services": []}),
            patch.object(diagnostics, "invoke", side_effect=failure),
        ):
            report = diagnostics.live_check(role="planner")
        self.assertFalse(report["valid"])
        self.assertTrue(report["invocation"]["attempted"])
        self.assertEqual(report["invocation"]["failure_reason"], "provider unavailable")


if __name__ == "__main__":
    unittest.main()
