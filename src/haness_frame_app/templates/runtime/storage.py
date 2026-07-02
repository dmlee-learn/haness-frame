from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace"
STATE_FILE = WORKSPACE / "state.json"


def ensure_workspace() -> None:
    for rel in ["packs", "evidence", "decisions", "executions", "logs"]:
        (WORKSPACE / rel).mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, object]:
    ensure_workspace()
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, object]) -> None:
    ensure_workspace()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def read_text(rel_path: str, default: str = "") -> str:
    path = ROOT / rel_path
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(rel_path: str, content: str) -> pathlib.Path:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
