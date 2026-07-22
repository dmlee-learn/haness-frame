from __future__ import annotations

import datetime as dt
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

from haness_frame_app.templates.runtime import evidence_policy, storage


class EvidencePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        self.policy = {
            "min_records": 2,
            "min_distinct_urls": 2,
            "allowed_confidence": ["high", "medium"],
            "max_age_days": 3650,
            "max_future_skew_minutes": 10,
            "min_excerpt_chars": 20,
            "min_search_coverage_ratio": 0.0,
        }
        (self.root / "workspace" / "evidence-policy.json").write_text(
            json.dumps(self.policy),
            encoding="utf-8",
        )
        self.patcher = patch.object(storage, "ROOT", self.root)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def record(url: str, confidence: str = "high", retrieved_at: str = "") -> dict[str, str]:
        return {
            "url": url,
            "confidence": confidence,
            "excerpt": "A sufficiently detailed evidence excerpt for validation.",
            "retrieved_at": retrieved_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def test_two_distinct_current_records_pass(self) -> None:
        result = evidence_policy.evaluate_evidence_policy(
            [self.record("https://example.com/a"), self.record("https://example.org/b", "medium")]
        )
        self.assertTrue(result["valid"])

    def test_rejects_disallowed_confidence(self) -> None:
        result = evidence_policy.evaluate_evidence_policy(
            [self.record("https://example.com/a", "low"), self.record("https://example.org/b")]
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("confidence" in issue for issue in result["issues"]))

    def test_rejects_normalized_duplicate_urls(self) -> None:
        result = evidence_policy.evaluate_evidence_policy(
            [self.record("https://EXAMPLE.com/a/"), self.record("https://example.com/a")]
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicate normalized" in issue for issue in result["issues"]))

    def test_rejects_future_timestamp(self) -> None:
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        result = evidence_policy.evaluate_evidence_policy(
            [self.record("https://example.com/a", retrieved_at=future), self.record("https://example.org/b")]
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("future" in issue for issue in result["issues"]))

    def test_enforces_configured_search_coverage(self) -> None:
        self.policy["min_search_coverage_ratio"] = 0.5
        (self.root / "workspace" / "evidence-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        result = evidence_policy.evaluate_evidence_policy(
            [self.record("https://example.com/a"), self.record("https://example.org/b")],
            planned_searches=4,
            covered_searches=1,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("coverage" in issue for issue in result["issues"]))

    def test_direct_url_fingerprint_can_be_required(self) -> None:
        self.policy["require_source_fingerprint"] = True
        (self.root / "workspace" / "evidence-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        first = self.record("https://example.com/a")
        first["provider"] = "direct_url"
        second = self.record("https://example.org/b")
        second["provider"] = "manual"
        missing = evidence_policy.evaluate_evidence_policy([first, second])
        self.assertFalse(missing["valid"])
        self.assertTrue(any("fingerprint is required" in issue for issue in missing["issues"]))
        first["source_sha256"] = "a" * 64
        self.assertTrue(evidence_policy.evaluate_evidence_policy([first, second])["valid"])

    def test_invalid_source_fingerprint_is_rejected(self) -> None:
        first = self.record("https://example.com/a")
        first["source_sha256"] = "not-a-sha256"
        result = evidence_policy.evaluate_evidence_policy([first, self.record("https://example.org/b")])
        self.assertFalse(result["valid"])
        self.assertTrue(any("source_sha256 is invalid" in issue for issue in result["issues"]))

    def test_source_revalidation_can_be_required(self) -> None:
        self.policy["require_source_revalidation"] = True
        self.policy["max_source_verification_age_days"] = 30
        (self.root / "workspace" / "evidence-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        first = self.record("https://example.com/a")
        first["source_sha256"] = "b" * 64
        missing = evidence_policy.evaluate_evidence_policy([first, self.record("https://example.org/b")])
        self.assertTrue(any("revalidation is required" in issue for issue in missing["issues"]))

        digest = evidence_policy.hashlib.sha256(
            evidence_policy._normalized_url(first["url"]).encode("utf-8")
        ).hexdigest()[:12]
        path = self.root / "workspace" / "evidence" / "source-verifications" / f"latest-{digest}.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "valid": True,
                    "status": "unchanged",
                    "expected_sha256": first["source_sha256"],
                    "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(evidence_policy.evaluate_evidence_policy([first, self.record("https://example.org/b")])["valid"])


if __name__ == "__main__":
    unittest.main()
