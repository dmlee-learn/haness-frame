from __future__ import annotations

import json
from pathlib import PurePosixPath

from .scorecard import mark_check
from .storage import ROOT

MANIFEST_FILE = "workspace/manifest.json"


def load_manifest() -> dict[str, object]:
    path = ROOT / MANIFEST_FILE
    if not path.is_file() or path.is_symlink():
        raise ValueError("workspace/manifest.json is missing or is not a regular file")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"workspace/manifest.json contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError("workspace/manifest.json root must be a JSON object")
    return manifest


def _safe_manifest_path(value: str) -> PurePosixPath | None:
    if not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0].endswith(":"):
        return None
    return path


def validate_manifest() -> dict[str, object]:
    issues: list[str] = []
    try:
        manifest = load_manifest()
    except (OSError, ValueError) as exc:
        manifest = {}
        issues.append(str(exc))
    project_name = manifest.get("project_name")
    if manifest and (not isinstance(project_name, str) or not project_name.strip()):
        issues.append("manifest project_name must be a non-empty string")
    format_version = manifest.get("format_version")
    if manifest and (not isinstance(format_version, str) or not format_version.strip()):
        issues.append("manifest format_version must be a non-empty string")
    files = manifest.get("files", [])
    if not isinstance(files, list):
        issues.append("manifest files must be a list")
        files = []
    elif not files:
        issues.append("manifest files must not be empty")
    seen: set[str] = set()
    checked = 0
    for rel_path in files:
        if not isinstance(rel_path, str) or not rel_path.strip():
            issues.append("manifest file entries must be non-empty strings")
            continue
        normalized = _safe_manifest_path(rel_path.strip())
        if normalized is None:
            issues.append(f"unsafe manifest file path: {rel_path}")
            continue
        normalized_text = normalized.as_posix()
        if normalized_text in seen:
            issues.append(f"duplicate manifest file path: {normalized_text}")
            continue
        seen.add(normalized_text)
        candidate = ROOT.joinpath(*normalized.parts)
        try:
            candidate.resolve(strict=False).relative_to(ROOT.resolve())
        except ValueError:
            issues.append(f"manifest file escapes project root: {normalized_text}")
            continue
        if candidate.is_symlink():
            issues.append(f"manifest file must not be a symlink: {normalized_text}")
        elif not candidate.is_file():
            issues.append(f"missing manifest file: {normalized_text}")
        else:
            checked += 1
    result = {
        "valid": not issues,
        "issues": issues,
        "checked_files": checked,
        "declared_files": len(files),
        "format_version": manifest.get("format_version", ""),
    }
    mark_check("manifest", bool(result["valid"]), "; ".join(issues[:3]))
    return result


def manifest_report() -> str:
    return json.dumps(validate_manifest(), indent=2, ensure_ascii=False)


def print_manifest_report() -> int:
    report = validate_manifest()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1
