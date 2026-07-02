from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

from .audit import log_event
from .scorecard import mark_check
from .storage import ROOT, WORKSPACE, ensure_workspace


def create_archive(label: str = "") -> Path:
    ensure_workspace()
    archive_dir = WORKSPACE / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.strip())[:48]
    name = f"{ROOT.name}-{stamp}{('-' + safe_label) if safe_label else ''}.zip"
    archive_path = archive_dir / name
    skip_parts = {"__pycache__", ".git", "archives"}
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(ROOT.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(ROOT)
            if any(part in skip_parts for part in rel.parts):
                continue
            archive.write(item, arcname=f"{ROOT.name}/{rel.as_posix()}")
    mark_check("archive", True, archive_path.name)
    log_event("archive.created", path=str(archive_path), label=label)
    return archive_path
