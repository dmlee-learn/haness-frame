from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import zipfile
from io import BytesIO

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "harness.yaml"
ROLES = ROOT / "config" / "roles.yaml"
DESIGN_LOOP = ROOT / "config" / "design_loop.yaml"
RUNS = ROOT / "runs"
PROJECTS = ROOT / "projects"
DATA = ROOT / "data"
DB = DATA / "haness.db"
LANG_DIR = ROOT / "lang"


def read_config_text() -> str:
    return CONFIG.read_text(encoding="utf-8")


def task_text(parts: list[str]) -> str:
    text = " ".join(parts).strip()
    if not text:
        raise SystemExit("task is required")
    return text


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:48] or "design"


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_project_doc(prefix: str, project: str, task: str, content: str) -> pathlib.Path:
    project_slug = slugify(project or task)
    docs_dir = PROJECTS / project_slug / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"{prefix}-{now_stamp()}-{slugify(task)}.md"
    path.write_text(content, encoding="utf-8")
    return path


def project_dir(project: str, task: str) -> pathlib.Path:
    return PROJECTS / slugify(project or task)


def safe_project_path(name: str) -> pathlib.Path | None:
    slug = slugify(name)
    if not slug or slug != name:
        return None
    path = (PROJECTS / slug).resolve()
    root = PROJECTS.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def list_projects() -> list[dict[str, str]]:
    PROJECTS.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(PROJECTS.iterdir()):
        if not path.is_dir():
            continue
        readme = path / "README.md"
        updated = dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        description = ""
        if readme.exists():
            text = readme.read_text(encoding="utf-8", errors="replace")
            marker = "## Working Description"
            if marker in text:
                description = text.split(marker, 1)[1].split("##", 1)[0].strip()
        projects.append({"name": path.name, "updated": updated, "description": description})
    return projects


def project_file_rows(path: pathlib.Path) -> list[dict[str, str]]:
    rows = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rows.append({"path": item.relative_to(path).as_posix(), "size": str(item.stat().st_size)})
    return rows


def project_zip_bytes(path: pathlib.Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(path.rglob("*")):
            if not item.is_file():
                continue
            archive.write(item, arcname=f"{path.name}/{item.relative_to(path).as_posix()}")
    return buffer.getvalue()


def write_project_file(path: pathlib.Path, content: str, overwrite: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    path.write_text(content, encoding="utf-8")
    return True
