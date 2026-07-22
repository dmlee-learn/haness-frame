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

from haness_frame_app.templates.runtime import audit, search_discovery, storage


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


class SearchDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace" / "evidence").mkdir(parents=True)
        (self.root / "workspace" / "scorecard.json").write_text("{}", encoding="utf-8")
        self.policy = {
            "enabled": True,
            "provider": "searxng",
            "base_url": "http://127.0.0.1:8888",
            "allow_private_network": True,
            "allowed_domains": [],
            "max_queries_per_run": 1,
            "max_results_per_query": 3,
            "timeout_seconds": 5,
            "max_response_bytes": 10000,
            "language": "all",
            "categories": "general",
            "safesearch": 1,
        }
        self.write_policy()
        (self.root / "workspace" / "evidence" / "search-plan.json").write_text(
            json.dumps({"searches": [{"query": "first query"}, {"query": "second query"}]}),
            encoding="utf-8",
        )
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

    def write_policy(self) -> None:
        (self.root / "workspace" / "search-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")

    def test_disabled_policy_refuses_network_request(self) -> None:
        self.policy["enabled"] = False
        self.write_policy()
        with patch.object(search_discovery, "_open_search") as request:
            with self.assertRaisesRegex(ValueError, "disabled"):
                search_discovery.discover_sources("query")
        request.assert_not_called()

    def test_plan_limit_and_candidate_deduplication(self) -> None:
        response = _Response(
            {
                "results": [
                    {"url": "https://Example.com/source#one", "title": " One  Source ", "content": " useful  text ", "engines": ["a"]},
                    {"url": "https://example.com/source#two", "title": "duplicate"},
                    {"url": "file:///tmp/not-web", "title": "invalid"},
                    {"url": "https://example.org/second", "title": "Second", "content": "more", "engine": "b"},
                ]
            }
        )
        with patch.object(search_discovery, "_open_search", return_value=response) as request:
            report = search_discovery.discover_sources()
        request.assert_called_once()
        self.assertEqual(report["searched"][0]["query"], "first query")
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["candidates"][0]["url"], "https://example.com/source")
        self.assertFalse(report["candidates"][0]["approved_evidence"])
        self.assertTrue((self.root / "workspace" / "evidence" / "discoveries" / "latest.json").is_file())

    def test_response_requires_results_list(self) -> None:
        with patch.object(search_discovery, "_open_search", return_value=_Response({"answers": []})):
            with self.assertRaisesRegex(ValueError, "results list"):
                search_discovery.discover_sources("query")


if __name__ == "__main__":
    unittest.main()
