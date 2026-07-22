from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import audit, evidence_fetch, evidence_policy, network_safety, storage


class _Response:
    def __init__(self, payload: bytes, url: str = "https://docs.example.com/source") -> None:
        self.payload = payload
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


class EvidenceFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text("[]", encoding="utf-8")
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.policy = {
            "fetch_enabled": True,
            "fetch_timeout_seconds": 5,
            "fetch_max_bytes": 4096,
            "fetch_excerpt_chars": 200,
            "fetch_allowed_content_types": ["text/html"],
            "fetch_allowed_domains": [],
            "allow_private_network": False,
        }
        (self.root / "workspace" / "evidence-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
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

    def fetch(self) -> dict[str, object]:
        return evidence_fetch.fetch_evidence(
            url="https://docs.example.com/source",
            query="safe harness evidence",
            why_it_matters="It defines the behavior being implemented.",
            recommended_use="Use this source to constrain the design.",
        )

    def test_fetch_extracts_html_and_commits_evidence(self) -> None:
        response = _Response(b"<html><title>Source Title</title><body>Useful evidence text for the design.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=response
        ):
            result = self.fetch()
        self.assertEqual(result["record"]["title"], "Source Title")
        self.assertIn("Useful evidence text", result["record"]["excerpt"])
        self.assertRegex(result["record"]["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["record"]["source_content_type"], "text/html")
        records = json.loads((self.root / "workspace" / "evidence" / "search-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(len(records), 1)

    def test_source_check_detects_unchanged_and_changed_content(self) -> None:
        original = _Response(b"<html><body>Stable evidence content for verification.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=original
        ):
            self.fetch()

        unchanged_response = _Response(b"<html><body>Stable   evidence content for verification.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=unchanged_response
        ):
            unchanged = evidence_fetch.verify_evidence_source("https://docs.example.com/source")
        self.assertTrue(unchanged["valid"])
        self.assertEqual(unchanged["status"], "unchanged")

        changed_response = _Response(b"<html><body>Materially changed source content.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=changed_response
        ):
            changed = evidence_fetch.verify_evidence_source("https://docs.example.com/source")
        self.assertFalse(changed["valid"])
        self.assertEqual(changed["status"], "content_changed")
        self.assertNotIn("Materially changed", json.dumps(changed))
        self.assertTrue((self.root / "workspace" / "evidence" / "source-verifications" / "latest.json").is_file())
        records = json.loads((self.root / "workspace" / "evidence" / "search-evidence.json").read_text(encoding="utf-8"))
        policy_report = evidence_policy.evaluate_evidence_policy(records)
        self.assertTrue(any("source changed" in issue for issue in policy_report["issues"]))

    def test_source_refresh_replaces_record_and_resolves_change_report(self) -> None:
        original = _Response(b"<html><body>Original evidence content for verification.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=original
        ):
            fetched = self.fetch()
        old_hash = fetched["record"]["source_sha256"]

        changed_response = _Response(b"<html><body>Reviewed replacement evidence content.</body></html>")
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=changed_response
        ):
            refreshed = evidence_fetch.refresh_evidence_source("https://docs.example.com/source")

        self.assertEqual(refreshed["verification"]["status"], "refreshed")
        self.assertNotEqual(refreshed["record"]["source_sha256"], old_hash)
        self.assertIn("Reviewed replacement", refreshed["record"]["excerpt"])
        records = json.loads((self.root / "workspace" / "evidence" / "search-evidence.json").read_text(encoding="utf-8"))
        policy_report = evidence_policy.evaluate_evidence_policy(records)
        self.assertFalse(any("source changed" in issue for issue in policy_report["issues"]))

    def test_source_check_requires_fingerprinted_record(self) -> None:
        records = [
            {
                "url": "https://docs.example.com/source",
                "provider": "manual",
                "title": "Manual source",
            }
        ]
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text(
            json.dumps(records), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "no valid fingerprint"):
            evidence_fetch.verify_evidence_source("https://docs.example.com/source")

    def test_check_all_continues_and_reports_changed_sources(self) -> None:
        records = [
            {
                "url": "https://docs.example.com/one",
                "source_sha256": hashlib.sha256(b"First stable content.").hexdigest(),
            },
            {
                "url": "https://docs.example.com/two",
                "source_sha256": hashlib.sha256(b"Original second content.").hexdigest(),
            },
        ]
        (self.root / "workspace" / "evidence" / "search-evidence.json").write_text(
            json.dumps(records), encoding="utf-8"
        )

        def open_source(url: str, timeout: float, policy: dict[str, object]) -> _Response:
            if url.endswith("/one"):
                return _Response(b"<html><body>First stable content.</body></html>", url)
            return _Response(b"<html><body>Changed second content.</body></html>", url)

        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", side_effect=open_source
        ):
            report = evidence_fetch.verify_all_evidence_sources()

        self.assertFalse(report["valid"])
        self.assertEqual((report["checked"], report["unchanged"], report["changed_or_failed"]), (2, 1, 1))
        self.assertEqual([item["status"] for item in report["results"]], ["unchanged", "content_changed"])
        self.assertTrue(
            (self.root / "workspace" / "evidence" / "source-verifications" / "latest-batch.json").is_file()
        )
        self.assertNotIn("Changed second content", json.dumps(report))

    def test_check_all_enforces_policy_limit(self) -> None:
        self.policy["max_source_checks_per_run"] = 1
        (self.root / "workspace" / "evidence-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "between 1 and 1"):
            evidence_fetch.verify_all_evidence_sources(limit=2)

    def test_private_network_address_is_blocked(self) -> None:
        resolved = [(2, 1, 6, "", ("127.0.0.1", 80))]
        with patch.object(network_safety.socket, "getaddrinfo", return_value=resolved):
            with self.assertRaisesRegex(ValueError, "non-public"):
                evidence_fetch._validate_target("http://localhost/source", self.policy)

    def test_domain_allowlist_is_enforced_before_request(self) -> None:
        self.policy["fetch_allowed_domains"] = ["trusted.example"]
        with self.assertRaisesRegex(ValueError, "domain is not allowed"):
            evidence_fetch._validate_target("https://untrusted.example/source", self.policy)

    def test_oversized_response_is_rejected_without_evidence(self) -> None:
        response = _Response(b"x" * 5000)
        with patch.object(evidence_fetch, "_validate_target", side_effect=lambda url, policy: url), patch.object(
            evidence_fetch, "_open_url", return_value=response
        ):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                self.fetch()
        records = json.loads((self.root / "workspace" / "evidence" / "search-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
