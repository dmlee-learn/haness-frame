from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import ai_cache, audit, storage


class AiCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "workspace").mkdir(parents=True)
        self.patchers = [
            patch.object(storage, "ROOT", self.root),
            patch.object(storage, "WORKSPACE", self.root / "workspace"),
            patch.object(storage, "STATE_FILE", self.root / "workspace" / "state.json"),
            patch.object(audit, "ROOT", self.root),
            patch.object(ai_cache, "role_service", return_value={"name": "local", "model": "model-a"}),
            patch.object(ai_cache, "fallback_service", return_value={}),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_second_identical_invocation_uses_cache(self) -> None:
        response = {
            "content": "diagnosis",
            "provider_type": "local",
            "service": {"name": "local"},
            "diagnostics": {"used_fallback": False, "attempts": [{"outcome": "success"}]},
        }
        with patch.object(ai_cache, "invoke", return_value=response) as invoke:
            first = ai_cache.invoke_cached("debugger", "same prompt")
            second = ai_cache.invoke_cached("debugger", "same prompt")

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["diagnostics"], response["diagnostics"])
        invoke.assert_called_once()

    def test_changed_prompt_does_not_reuse_cache(self) -> None:
        response = {"content": "result", "provider_type": "local", "service": {"name": "local"}}
        with patch.object(ai_cache, "invoke", return_value=response) as invoke:
            ai_cache.invoke_cached("coder", "prompt one")
            ai_cache.invoke_cached("coder", "prompt two")
        self.assertEqual(invoke.call_count, 2)

    def test_equivalent_service_aliases_share_canonical_cache_key(self) -> None:
        left = {
            "name": "primary",
            "provider_type": "openai",
            "base_url": "HTTP://LOCALHOST:80/v1/",
            "model": "model-a",
            "enabled": True,
        }
        right = {
            **left,
            "name": "renamed",
            "provider_type": "vllm",
            "base_url": "http://localhost/v1",
        }
        with patch.object(ai_cache, "role_service", return_value=left):
            first = ai_cache.cache_key("coder", "same prompt")
        with patch.object(ai_cache, "role_service", return_value=right):
            second = ai_cache.cache_key("coder", "same prompt")
        self.assertEqual(first, second)

    def test_disabled_service_does_not_reuse_enabled_cache(self) -> None:
        enabled = {
            "name": "local",
            "provider_type": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "model-a",
            "enabled": True,
        }
        disabled = {**enabled, "enabled": False}
        response = {"content": "result", "provider_type": "ollama", "service": enabled}
        with patch.object(ai_cache, "role_service", return_value=enabled):
            ai_cache.invoke_cached("coder", "enabled state", invoke_fn=lambda *args, **kwargs: response)
        calls = 0

        def provider(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return response

        with patch.object(ai_cache, "role_service", return_value=disabled):
            result = ai_cache.invoke_cached("coder", "enabled state", invoke_fn=provider)
        self.assertEqual(calls, 1)
        self.assertFalse(result["cache_hit"])

    def test_api_key_rotation_invalidates_cache_without_storing_fingerprint(self) -> None:
        service = {
            "name": "remote",
            "provider_type": "openai",
            "base_url": "https://example.com/v1",
            "model": "model-a",
            "api_key_env": "HANESS_CACHE_TEST_KEY",
            "enabled": True,
        }
        response = {"content": "result", "provider_type": "openai", "service": service}
        with patch.object(ai_cache, "role_service", return_value=service), patch.dict(
            "os.environ", {"HANESS_CACHE_TEST_KEY": "first-secret"}, clear=False
        ):
            first = ai_cache.invoke_cached("coder", "credential rotation", invoke_fn=lambda *args, **kwargs: response)
        calls = 0

        def provider(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return response

        with patch.object(ai_cache, "role_service", return_value=service), patch.dict(
            "os.environ", {"HANESS_CACHE_TEST_KEY": "second-secret"}, clear=False
        ):
            second = ai_cache.invoke_cached("coder", "credential rotation", invoke_fn=provider)
        self.assertFalse(first["cache_hit"])
        self.assertFalse(second["cache_hit"])
        self.assertEqual(calls, 1)
        cache_root = self.root / "workspace" / "cache" / "ai"
        cache_text = "".join(path.read_text(encoding="utf-8") for path in cache_root.glob("*.json"))
        self.assertNotIn("credential_sha256", cache_text)
        self.assertNotIn("first-secret", cache_text)
        self.assertNotIn("second-secret", cache_text)

    def test_disabled_cache_always_invokes_provider(self) -> None:
        response = {"content": "result", "provider_type": "local", "service": {"name": "local"}}
        with patch.object(ai_cache, "invoke", return_value=response) as invoke:
            ai_cache.invoke_cached("reviewer", "prompt", enabled=False)
            ai_cache.invoke_cached("reviewer", "prompt", enabled=False)
        self.assertEqual(invoke.call_count, 2)

    def test_invalid_content_is_not_cached(self) -> None:
        responses = [
            {"content": "short", "provider_type": "local"},
            {"content": "a sufficiently detailed response", "provider_type": "local"},
        ]

        def validate(content: str) -> str:
            if len(content) < 20:
                raise ValueError("response is too short")
            return content

        with patch.object(ai_cache, "invoke", side_effect=responses) as invoke:
            with self.assertRaisesRegex(ValueError, "too short"):
                ai_cache.invoke_cached("planner", "validate output", content_validator=validate)
            result = ai_cache.invoke_cached("planner", "validate output", content_validator=validate)
        self.assertEqual(result["content"], "a sufficiently detailed response")
        self.assertEqual(invoke.call_count, 2)

    def test_concurrent_identical_invocations_share_provider_call(self) -> None:
        call_count = 0
        count_lock = threading.Lock()

        def provider(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal call_count
            with count_lock:
                call_count += 1
            time.sleep(0.1)
            return {"content": "shared result", "provider_type": "local"}

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(
                    ai_cache.invoke_cached,
                    "coder",
                    "one concurrent prompt",
                    invoke_fn=provider,
                )
                for _ in range(4)
            ]
            results = [future.result() for future in futures]

        self.assertEqual(call_count, 1)
        self.assertEqual(sum(not result["cache_hit"] for result in results), 1)
        self.assertEqual(sum(bool(result["cache_hit"]) for result in results), 3)
        self.assertEqual({result["content"] for result in results}, {"shared result"})

    def test_provider_failure_is_not_cached(self) -> None:
        calls = 0

        def provider(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("provider unavailable")
            return {"content": "recovered", "provider_type": "local"}

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            ai_cache.invoke_cached("coder", "retry after failure", invoke_fn=provider)
        result = ai_cache.invoke_cached("coder", "retry after failure", invoke_fn=provider)

        self.assertEqual(calls, 2)
        self.assertFalse(result["cache_hit"])

    def test_tampered_cached_result_is_not_reused(self) -> None:
        original = {"content": "original result", "provider_type": "local", "service": {"name": "local"}}
        replacement = {"content": "replacement result", "provider_type": "local", "service": {"name": "local"}}
        ai_cache.invoke_cached("coder", "tamper check", invoke_fn=lambda *args, **kwargs: original)
        cache_path = next((self.root / "workspace" / "cache" / "ai").glob("*.json"))
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["result"]["content"] = "tampered result"
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        calls = 0

        def provider(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return replacement

        result = ai_cache.invoke_cached("coder", "tamper check", invoke_fn=provider)
        self.assertEqual(calls, 1)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["content"], "replacement result")

    def test_cache_status_rejects_swapped_key_binding(self) -> None:
        response = {"content": "bound result", "provider_type": "local"}
        ai_cache.invoke_cached("coder", "bound prompt", invoke_fn=lambda *args, **kwargs: response)
        cache_path = next((self.root / "workspace" / "cache" / "ai").glob("*.json"))
        swapped = cache_path.with_name("f" * 64 + ".json")
        cache_path.replace(swapped)
        status = ai_cache.cache_status()
        self.assertEqual(status["invalid"], 1)

    def test_separate_processes_share_one_provider_call(self) -> None:
        counter_path = self.root / "provider-calls.txt"
        script = """
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from haness_frame_app.templates.runtime import ai_cache, audit, storage

root = Path(sys.argv[1])
storage.ROOT = root
storage.WORKSPACE = root / "workspace"
storage.STATE_FILE = storage.WORKSPACE / "state.json"
audit.ROOT = root
ai_cache.role_service = lambda role: {"name": "local", "model": "model-a"}
ai_cache.fallback_service = lambda: {}

def provider(*args, **kwargs):
    with (root / "provider-calls.txt").open("a", encoding="utf-8") as handle:
        handle.write("called\\n")
        handle.flush()
    time.sleep(0.3)
    return {"content": "cross-process result", "provider_type": "local"}

result = ai_cache.invoke_cached(
    "coder",
    "cross-process prompt",
    invoke_fn=provider,
    singleflight_timeout_seconds=5.0,
)
print(json.dumps({"cache_hit": result["cache_hit"], "content": result["content"]}))
"""
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(self.root), str(SRC)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs: list[dict[str, object]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            outputs.append(json.loads(stdout))

        self.assertEqual(counter_path.read_text(encoding="utf-8").splitlines(), ["called"])
        self.assertEqual(sum(not output["cache_hit"] for output in outputs), 1)
        self.assertEqual(sum(bool(output["cache_hit"]) for output in outputs), 1)
        self.assertEqual({output["content"] for output in outputs}, {"cross-process result"})

    def test_cache_status_and_prune_do_not_expose_content(self) -> None:
        response = {"content": "sensitive response", "provider_type": "local"}
        ai_cache.invoke_cached("coder", "fresh prompt", invoke_fn=lambda *args, **kwargs: response)
        ai_cache.invoke_cached("coder", "stale prompt", invoke_fn=lambda *args, **kwargs: response)
        cache_files = sorted((self.root / "workspace" / "cache" / "ai").glob("*.json"))
        stale_payload = json.loads(cache_files[1].read_text(encoding="utf-8"))
        stale_payload["created_epoch"] = time.time() - 120
        cache_files[1].write_text(json.dumps(stale_payload), encoding="utf-8")
        (cache_files[0].parent / "broken.json").write_text("{broken", encoding="utf-8")

        status = ai_cache.cache_status(max_age_seconds=60)
        self.assertEqual((status["fresh"], status["stale"], status["invalid"]), (1, 1, 1))
        self.assertNotIn("sensitive response", json.dumps(status))

        pruned = ai_cache.prune_cache(max_age_seconds=60)
        self.assertEqual(pruned["removed_by_state"], {"fresh": 0, "stale": 1, "invalid": 1})
        self.assertEqual(pruned["remaining"]["fresh"], 1)
        cleared = ai_cache.prune_cache(max_age_seconds=60, include_fresh=True)
        self.assertEqual(cleared["removed_by_state"]["fresh"], 1)
        self.assertEqual(cleared["remaining"]["entries"], 0)

    def test_cache_status_rejects_invalid_age(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            ai_cache.cache_status(0)
        with self.assertRaisesRegex(ValueError, "at least 1"):
            ai_cache.prune_cache(-1)


if __name__ == "__main__":
    unittest.main()
