from __future__ import annotations

import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

from .audit import log_event
from .scorecard import mark_check
from .storage import ROOT, WORKSPACE, ensure_workspace

INCLUDE_DIRS = ["context", "docs", "research", "prompts", "implementation", "workspace"]
SKIP_DIR_NAMES = {"snapshots", "__pycache__"}


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def _snapshot_root() -> Path:
    ensure_workspace()
    path = WORKSPACE / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        return
    for item in source.rglob("*"):
        rel = item.relative_to(source)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        destination = target / rel
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def create_snapshot(label: str = "") -> dict[str, object]:
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.strip())[:48]
    name = f"{_stamp()}{('-' + safe_label) if safe_label else ''}"
    root = _snapshot_root() / name
    root.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    for rel_dir in INCLUDE_DIRS:
        source = ROOT / rel_dir
        if source.exists():
            _copy_tree(source, root / rel_dir)
            copied.append(rel_dir)
    metadata = {
        "name": name,
        "label": label,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "copied": copied,
    }
    (root / "snapshot.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    mark_check("snapshot", True, name)
    log_event("snapshot.created", name=name, label=label)
    return metadata


def list_snapshots() -> list[dict[str, object]]:
    root = _snapshot_root()
    snapshots: list[dict[str, object]] = []
    for item in sorted(root.iterdir()):
        if not item.is_dir():
            continue
        metadata_path = item / "snapshot.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {"name": item.name}
        else:
            metadata = {"name": item.name}
        snapshots.append(metadata)
    return snapshots


def restore_snapshot(name: str) -> dict[str, object]:
    snapshot = (_snapshot_root() / name).resolve()
    try:
        snapshot.relative_to(_snapshot_root().resolve())
    except ValueError as exc:
        raise ValueError("snapshot name escapes snapshot directory") from exc
    if not snapshot.exists() or not snapshot.is_dir():
        raise ValueError(f"snapshot not found: {name}")
    temp_root = Path(tempfile.mkdtemp(prefix="haness-restore-"))
    shutil.copytree(snapshot, temp_root / "snapshot")
    source_root = temp_root / "snapshot"
    restored: list[str] = []
    for rel_dir in INCLUDE_DIRS:
        source = source_root / rel_dir
        if not source.exists():
            continue
        target = ROOT / rel_dir
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        restored.append(rel_dir)
    mark_check("rollback", True, name)
    log_event("snapshot.restored", name=name, restored=restored)
    return {"restored": restored, "name": name}
