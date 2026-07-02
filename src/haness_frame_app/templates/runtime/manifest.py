from __future__ import annotations

import json

from .scorecard import mark_check
from .storage import ROOT, read_text


def load_manifest() -> dict[str, object]:
    payload = read_text("workspace/manifest.json", "{}")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return manifest if isinstance(manifest, dict) else {}


def validate_manifest() -> dict[str, object]:
    manifest = load_manifest()
    issues: list[str] = []
    files = manifest.get("files", [])
    if not isinstance(files, list):
        issues.append("manifest files must be a list")
        files = []
    for rel_path in files:
        if not isinstance(rel_path, str) or not rel_path.strip():
            issues.append(f"invalid manifest file entry: {rel_path!r}")
            continue
        if not (ROOT / rel_path).exists():
            issues.append(f"missing manifest file: {rel_path}")
    result = {
        "valid": not issues,
        "issues": issues,
        "checked_files": len(files),
        "format_version": manifest.get("format_version", ""),
    }
    mark_check("manifest", bool(result["valid"]), "; ".join(issues[:3]))
    return result


def manifest_report() -> str:
    return json.dumps(validate_manifest(), indent=2, ensure_ascii=False)
