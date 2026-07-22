from __future__ import annotations

import json
import hashlib
import datetime as dt
import os
import pathlib
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace"
STATE_FILE = WORKSPACE / "state.json"
LOCK_TIMEOUT_SECONDS = 10.0
STALE_LOCK_SECONDS = 60.0
MUTATION_LOCK_TIMEOUT_SECONDS = 10.0


def ensure_workspace() -> None:
    for rel in ["packs", "evidence", "decisions", "executions", "logs"]:
        (WORKSPACE / rel).mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, object]:
    ensure_workspace()
    return _load_json_object_path(STATE_FILE)


def load_json_object(rel_path: str) -> dict[str, object]:
    return _load_json_object_path(ROOT / rel_path)


def _path_label(path: pathlib.Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _load_json_object_path(path: pathlib.Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{_path_label(path)} contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{_path_label(path)} root must be a JSON object")
    return payload


def save_state(state: dict[str, object]) -> None:
    ensure_workspace()
    write_path_text(STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False))


def read_text(rel_path: str, default: str = "") -> str:
    path = ROOT / rel_path
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def _checkpoint_time(path: pathlib.Path) -> float:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for field in ("updated_at", "completed_at", "created_at"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def read_latest_session(latest_rel_path: str, sessions_root_rel_path: str, default: str = "") -> str:
    latest = ROOT / latest_rel_path
    sessions_root = ROOT / sessions_root_rel_path
    candidates = [latest] if latest.is_file() and not latest.is_symlink() else []
    if sessions_root.is_dir() and not sessions_root.is_symlink():
        candidates.extend(
            path
            for path in sessions_root.glob("*/session.json")
            if path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        )
    if not candidates:
        return default
    selected = max(candidates, key=lambda path: (_checkpoint_time(path), str(path)))
    return selected.read_text(encoding="utf-8", errors="replace")


def write_text(rel_path: str, content: str) -> pathlib.Path:
    path = ROOT / rel_path
    return write_path_text(path, content)


def _lock_path(path: pathlib.Path) -> pathlib.Path:
    lock_root = ROOT / "workspace" / ".locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    safe_name = path.name.replace(".", "-")[:40] or "file"
    identity = str(path.resolve()).encode("utf-8", errors="surrogatepass")
    return lock_root / f"{safe_name}-{hashlib.sha256(identity).hexdigest()[:20]}.lock"


def _owner_is_alive(lock_path: pathlib.Path) -> bool:
    try:
        fields = dict(
            part.split("=", 1)
            for part in lock_path.read_text(encoding="ascii").split()
            if "=" in part
        )
        pid = int(fields.get("pid", "0"))
    except (OSError, ValueError):
        return True
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return kernel32.GetLastError() == 5
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


@contextmanager
def file_lock(
    path: pathlib.Path,
    timeout: float = LOCK_TIMEOUT_SECONDS,
    *,
    stale_seconds: float | None = STALE_LOCK_SECONDS,
):
    lock_path = _lock_path(path)
    deadline = time.monotonic() + max(0.0, timeout)
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()} created={time.time()}\n".encode("ascii"))
            os.fsync(descriptor)
        except (FileExistsError, PermissionError):
            try:
                stale = (
                    not _owner_is_alive(lock_path)
                    if stale_seconds is None
                    else time.time() - lock_path.stat().st_mtime > stale_seconds
                )
            except FileNotFoundError:
                time.sleep(0.005)
                continue
            if stale:
                try:
                    lock_path.unlink()
                except (FileNotFoundError, PermissionError):
                    pass
                if not lock_path.exists():
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for file lock: {path}")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def operation_lock(category: str, identity: str, timeout: float = 0.2):
    target = ROOT / "workspace" / ".operations" / f"{category}-{identity}"
    try:
        with file_lock(target, timeout=timeout, stale_seconds=None):
            yield
    except TimeoutError as exc:
        raise RuntimeError(f"{category} session is already active: {identity}") from exc


def write_path_text(path: pathlib.Path, content: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        _replace_text(path, content)
    return path


def _replace_text(path: pathlib.Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = pathlib.Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def append_path_text(path: pathlib.Path, content: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    return path


def update_json_object(rel_path: str, mutator: Callable[[dict[str, object]], None]) -> dict[str, object]:
    return update_json_path(ROOT / rel_path, mutator)


def update_json_path(path: pathlib.Path, mutator: Callable[[dict[str, object]], None]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        current = _load_json_object_path(path)
        mutator(current)
        _replace_text(path, json.dumps(current, indent=2, ensure_ascii=False))
        return current
