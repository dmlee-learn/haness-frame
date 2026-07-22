from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime.services import (
    service_configuration_issues,
    service_execution_identity,
    service_request_timeout,
)


class ServiceIdentityTests(unittest.TestCase):
    def test_request_timeout_defaults_to_120_seconds(self) -> None:
        self.assertEqual(service_request_timeout({}), 120)

    def test_request_timeout_is_bounded_and_validated(self) -> None:
        self.assertEqual(service_request_timeout({"request_timeout_seconds": 240}), 240)
        base = {
            "provider_type": "openai_compatible",
            "base_url": "http://localhost:8000/v1",
            "model": "model-a",
        }
        for value in (True, 0, 601, 1.5):
            with self.subTest(value=value):
                issues = service_configuration_issues({**base, "request_timeout_seconds": value})
                self.assertTrue(any("request_timeout_seconds" in issue for issue in issues))

    def test_openai_adapter_aliases_and_equivalent_urls_are_canonical(self) -> None:
        left = {
            "provider_type": "openai_compatible",
            "base_url": "HTTP://LOCALHOST:80/v1/",
            "model": "model-a",
        }
        right = {
            "provider_type": "vllm",
            "base_url": "http://localhost/v1",
            "model": "model-a",
        }
        self.assertEqual(service_execution_identity(left), service_execution_identity(right))

    def test_https_default_port_is_removed(self) -> None:
        service = {
            "provider_type": "openai",
            "base_url": "https://EXAMPLE.com:443/v1/",
            "model": "model-a",
        }
        self.assertEqual(
            service_execution_identity(service),
            ("openai_compatible", "https://example.com/v1", "model-a"),
        )

    def test_endpoint_path_and_model_remain_identity_boundaries(self) -> None:
        base = {"provider_type": "openai", "base_url": "https://example.com/v1", "model": "model-a"}
        other_path = {**base, "base_url": "https://example.com/team/v1"}
        other_model = {**base, "model": "model-b"}
        self.assertNotEqual(service_execution_identity(base), service_execution_identity(other_path))
        self.assertNotEqual(service_execution_identity(base), service_execution_identity(other_model))


if __name__ == "__main__":
    unittest.main()
