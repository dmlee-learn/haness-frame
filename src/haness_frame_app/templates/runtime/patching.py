from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path, PurePosixPath

from .audit import log_event
from .engine import enforce_decision_gate
from .scorecard import mark_check
from .storage import ROOT, read_text, write_path_text, write_text

POLICY_FILE = "workspace/repair-policy.json"
PATCH_ROOT = "workspace/patches"
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_fresh(target: Path, payload: bytes) -> None:
    previous_mtime = target.stat().st_mtime if target.exists() else 0.0
    target.write_bytes(payload)
    stamp = max(time.time(), float(int(previous_mtime) + 1))
    os.utime(target, (stamp, stamp))


def load_repair_policy() -> dict[str, object]:
    try:
        policy = json.loads(read_text(POLICY_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid repair policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("repair policy must be a JSON object")
    roots = policy.get("editable_roots", [])
    if not isinstance(roots, list) or not roots or not all(isinstance(item, str) and item.strip() for item in roots):
        raise ValueError("repair policy editable_roots must be a non-empty string list")
    strict_review = policy.get("require_independent_reviewer_service", False)
    if not isinstance(strict_review, bool):
        raise ValueError("repair policy require_independent_reviewer_service must be a boolean")
    return policy


def _policy_int(policy: dict[str, object], name: str, default: int, minimum: int, maximum: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"repair policy {name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"repair policy {name} must be an integer") from exc
    return max(minimum, min(parsed, maximum))


def _diff_path(value: str) -> str:
    path = value.strip().split("\t", 1)[0].strip().replace("\\", "/")
    if path == "/dev/null":
        return path
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _editable_roots(policy: dict[str, object]) -> tuple[PurePosixPath, ...]:
    return tuple(PurePosixPath(item.strip().replace("\\", "/")) for item in policy["editable_roots"])


def _safe_target(rel_path: str, editable_roots: tuple[PurePosixPath, ...]) -> Path:
    pure = PurePosixPath(rel_path)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ValueError(f"patch path escapes the project: {rel_path}")
    if not any(pure == allowed or allowed in pure.parents for allowed in editable_roots):
        raise ValueError(f"patch path is outside editable roots: {rel_path}")
    root = ROOT.resolve()
    target = (ROOT / Path(*pure.parts)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"patch path escapes the project: {rel_path}") from exc
    return target


def parse_unified_diff(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    files: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        old_path = _diff_path(lines[index][4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValueError(f"missing new-file header after {old_path}")
        new_path = _diff_path(lines[index][4:])
        index += 1
        if new_path == "/dev/null":
            raise ValueError("file deletion patches are not allowed")
        hunks: list[dict[str, object]] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            match = _HUNK_HEADER.match(lines[index])
            if not match:
                index += 1
                continue
            hunk = {
                "old_start": int(match.group(1)),
                "old_count": int(match.group(2) or "1"),
                "new_start": int(match.group(3)),
                "new_count": int(match.group(4) or "1"),
                "lines": [],
            }
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.startswith(("@@ ", "--- ")):
                    break
                if line == "\\ No newline at end of file":
                    index += 1
                    continue
                if not line or line[0] not in {" ", "+", "-"}:
                    raise ValueError(f"invalid unified diff line: {line}")
                hunk["lines"].append((line[0], line[1:]))
                index += 1
            hunks.append(hunk)
        if not hunks:
            raise ValueError(f"patch has no hunks for {new_path}")
        files.append({"old_path": old_path, "new_path": new_path, "hunks": hunks})
    if not files:
        raise ValueError("no unified diff file sections found")
    return files


def _apply_hunks(source: str, hunks: list[dict[str, object]], path: str) -> str:
    newline = "\r\n" if "\r\n" in source else "\n"
    trailing_newline = source.endswith(("\n", "\r"))
    source_lines = source.splitlines()
    output: list[str] = []
    cursor = 0
    for hunk in hunks:
        target = max(0, int(hunk["old_start"]) - 1)
        if target < cursor or target > len(source_lines):
            raise ValueError(f"overlapping or invalid hunk position for {path}")
        output.extend(source_lines[cursor:target])
        cursor = target
        old_seen = 0
        new_seen = 0
        for operation, value in hunk["lines"]:
            if operation in {" ", "-"}:
                if cursor >= len(source_lines) or source_lines[cursor] != value:
                    raise ValueError(f"patch context mismatch for {path} at source line {cursor + 1}")
                old_seen += 1
                if operation == " ":
                    output.append(value)
                    new_seen += 1
                cursor += 1
            else:
                output.append(value)
                new_seen += 1
        if old_seen != int(hunk["old_count"]) or new_seen != int(hunk["new_count"]):
            raise ValueError(f"hunk line counts do not match header for {path}")
    output.extend(source_lines[cursor:])
    result = newline.join(output)
    if trailing_newline or (not source and output):
        result += newline
    return result


def patch_plan(text: str) -> dict[str, object]:
    policy = load_repair_policy()
    max_bytes = _policy_int(policy, "max_patch_bytes", 200000, 1000, 2000000)
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"patch exceeds max_patch_bytes: {len(encoded)} > {max_bytes}")
    sections = parse_unified_diff(text)
    max_files = _policy_int(policy, "max_patch_files", 20, 1, 200)
    if len(sections) > max_files:
        raise ValueError(f"patch exceeds max_patch_files: {len(sections)} > {max_files}")
    editable_roots = _editable_roots(policy)
    prepared = []
    seen: set[Path] = set()
    for section in sections:
        rel_path = str(section["new_path"])
        target = _safe_target(rel_path, editable_roots)
        if target in seen:
            raise ValueError(f"duplicate patch target: {rel_path}")
        seen.add(target)
        is_new = section["old_path"] == "/dev/null"
        if is_new and target.exists():
            raise ValueError(f"new-file patch target already exists: {rel_path}")
        if not is_new and not target.is_file():
            raise ValueError(f"patch target does not exist: {rel_path}")
        original_bytes = b"" if is_new else target.read_bytes()
        try:
            original = original_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"patch target is not UTF-8 text: {rel_path}") from exc
        updated = _apply_hunks(original, section["hunks"], rel_path)
        prepared.append(
            {
                "path": rel_path,
                "target": target,
                "is_new": is_new,
                "original_bytes": original_bytes,
                "updated_bytes": updated.encode("utf-8"),
            }
        )
    return {
        "valid": True,
        "patch_sha256": _sha256(encoded),
        "files": prepared,
        "file_count": len(prepared),
        "byte_count": len(encoded),
    }


def patch_plan_report(text: str) -> dict[str, object]:
    plan = patch_plan(text)
    return {
        "valid": True,
        "patch_sha256": plan["patch_sha256"],
        "file_count": plan["file_count"],
        "byte_count": plan["byte_count"],
        "files": [
            {"path": item["path"], "new_file": item["is_new"]}
            for item in plan["files"]
        ],
    }


def apply_patch_text(text: str) -> dict[str, object]:
    enforce_decision_gate("coder")
    plan = patch_plan(text)
    patch_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record_dir = ROOT / PATCH_ROOT / patch_id
    backup_dir = record_dir / "before"
    applied: list[dict[str, object]] = []
    log_event("patch.started", patch_id=patch_id, files=plan["file_count"])
    try:
        for item in plan["files"]:
            target = item["target"]
            if not item["is_new"]:
                backup = backup_dir / Path(*PurePosixPath(str(item["path"])).parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(item["original_bytes"])
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_fresh(target, item["updated_bytes"])
            applied.append(item)
    except OSError:
        for item in reversed(applied):
            target = item["target"]
            if item["is_new"]:
                target.unlink(missing_ok=True)
            else:
                _write_fresh(target, item["original_bytes"])
        raise
    metadata = {
        "patch_id": patch_id,
        "created_at": _now(),
        "patch_sha256": plan["patch_sha256"],
        "files": [
            {
                "path": item["path"],
                "new_file": item["is_new"],
                "before_sha256": _sha256(item["original_bytes"]),
                "after_sha256": _sha256(item["updated_bytes"]),
            }
            for item in plan["files"]
        ],
        "rolled_back": False,
    }
    record_dir.mkdir(parents=True, exist_ok=True)
    write_path_text(record_dir / "patch.diff", text)
    write_path_text(record_dir / "metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    write_text(f"{PATCH_ROOT}/latest.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    mark_check("patch_apply", True, f"{plan['file_count']} file(s), patch {patch_id}")
    log_event("patch.completed", patch_id=patch_id, files=plan["file_count"])
    return metadata


def patch_state(patch_id: str) -> dict[str, object]:
    if not re.fullmatch(r"\d{8}T\d{12}Z", patch_id):
        raise ValueError("invalid patch id")
    metadata_path = ROOT / PATCH_ROOT / patch_id / "metadata.json"
    if not metadata_path.is_file():
        raise ValueError(f"patch record not found: {patch_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("rolled_back"):
        return {"patch_id": patch_id, "state": "rolled_back", "conflicts": []}
    policy = load_repair_policy()
    editable_roots = _editable_roots(policy)
    conflicts = []
    for item in metadata.get("files", []):
        rel_path = str(item.get("path", ""))
        target = _safe_target(rel_path, editable_roots)
        current = target.read_bytes() if target.exists() else b""
        if _sha256(current) != item.get("after_sha256"):
            conflicts.append(rel_path)
    return {
        "patch_id": patch_id,
        "state": "conflict" if conflicts else "applied",
        "conflicts": conflicts,
    }


def rollback_patch(patch_id: str) -> dict[str, object]:
    if not re.fullmatch(r"\d{8}T\d{12}Z", patch_id):
        raise ValueError("invalid patch id")
    record_dir = ROOT / PATCH_ROOT / patch_id
    metadata_path = record_dir / "metadata.json"
    if not metadata_path.is_file():
        raise ValueError(f"patch record not found: {patch_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("rolled_back"):
        raise ValueError(f"patch already rolled back: {patch_id}")
    policy = load_repair_policy()
    editable_roots = _editable_roots(policy)
    prepared = []
    for item in metadata.get("files", []):
        rel_path = str(item.get("path", ""))
        target = _safe_target(rel_path, editable_roots)
        current = target.read_bytes() if target.exists() else b""
        if _sha256(current) != item.get("after_sha256"):
            raise ValueError(f"rollback conflict; file changed after patch: {rel_path}")
        backup = record_dir / "before" / Path(*PurePosixPath(rel_path).parts)
        prepared.append((item, target, backup))
    for item, target, backup in prepared:
        if item.get("new_file"):
            target.unlink(missing_ok=True)
        else:
            _write_fresh(target, backup.read_bytes())
    metadata["rolled_back"] = True
    metadata["rolled_back_at"] = _now()
    write_path_text(metadata_path, json.dumps(metadata, indent=2, ensure_ascii=False))
    mark_check("patch_rollback", True, f"patch {patch_id}")
    log_event("patch.rolled_back", patch_id=patch_id, files=len(prepared))
    return metadata


def load_patch_file(path: str) -> str:
    candidate = (ROOT / path).resolve(strict=True)
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("patch file must be inside the project") from exc
    if not candidate.is_file():
        raise ValueError(f"patch file not found: {path}")
    return candidate.read_text(encoding="utf-8")
