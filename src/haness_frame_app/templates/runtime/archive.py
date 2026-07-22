from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from .audit import log_event
from .scorecard import mark_check
from .storage import ROOT, WORKSPACE, ensure_workspace, read_text

POLICY_FILE = "workspace/archive-policy.json"
ARCHIVE_MANIFEST = "META-INF/haness-frame-manifest.json"
ARCHIVE_FORMAT_VERSION = 1
HASH_CHUNK_BYTES = 1024 * 1024


def _policy_int(policy: dict[str, object], name: str, default: int, low: int, high: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"archive policy {name} must be an integer")
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"archive policy {name} must be an integer") from exc


def load_archive_policy() -> dict[str, object]:
    try:
        policy = json.loads(read_text(POLICY_FILE, "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid archive policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("archive policy must be a JSON object")
    patterns = policy.get("exclude_globs", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) and item.strip() for item in patterns):
        raise ValueError("archive policy exclude_globs must be a string list")
    return policy


def _archive_files(policy: dict[str, object]) -> list[tuple[Path, Path]]:
    patterns = [str(item).replace("\\", "/") for item in policy.get("exclude_globs", [])]
    max_files = _policy_int(policy, "max_files", 10000, 1, 100000)
    max_file_bytes = _policy_int(policy, "max_file_bytes", 50_000_000, 1, 2_000_000_000)
    max_total_bytes = _policy_int(policy, "max_total_bytes", 500_000_000, 1, 10_000_000_000)
    selected: list[tuple[Path, Path]] = []
    total_bytes = 0
    for item in sorted(ROOT.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue
        rel = item.relative_to(ROOT)
        rel_text = rel.as_posix()
        if any(fnmatch.fnmatch(rel_text, pattern) for pattern in patterns):
            continue
        size = item.stat().st_size
        if size > max_file_bytes:
            raise ValueError(f"archive file exceeds max_file_bytes: {rel_text}")
        total_bytes += size
        if total_bytes > max_total_bytes:
            raise ValueError(f"archive content exceeds max_total_bytes: {total_bytes}")
        selected.append((item, rel))
        if len(selected) > max_files:
            raise ValueError(f"archive content exceeds max_files: {len(selected)}")
    return selected


def _member_is_safe(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and not path.parts[0].endswith(":")


def _hash_member(bundle: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with bundle.open(info, "r") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _build_archive_manifest(
    bundle: zipfile.ZipFile,
    *,
    label: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    total_bytes = 0
    for info in bundle.infolist():
        if info.is_dir():
            continue
        if info.file_size > max_file_bytes:
            raise ValueError(f"archived file exceeds max_file_bytes: {info.filename}")
        total_bytes += info.file_size
        if total_bytes > max_total_bytes:
            raise ValueError(f"archived content exceeds max_total_bytes: {total_bytes}")
        records.append(
            {
                "path": info.filename,
                "size": info.file_size,
                "sha256": _hash_member(bundle, info),
            }
        )
    return {
        "format": "haness-frame-archive",
        "format_version": ARCHIVE_FORMAT_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": ROOT.name,
        "label": label,
        "hash_algorithm": "sha256",
        "file_count": len(records),
        "total_bytes": total_bytes,
        "files": records,
    }


def _archive_path(value: str | Path) -> Path:
    if str(value).strip().lower() != "latest":
        return Path(value).expanduser().resolve()
    archive_dir = WORKSPACE / "archives"
    candidates = sorted(archive_dir.glob("*.zip"), key=lambda path: path.stat().st_mtime_ns)
    if not candidates:
        raise ValueError("no archive is available to verify")
    return candidates[-1]


def verify_archive(value: str | Path = "latest") -> dict[str, object]:
    archive_path = _archive_path(value)
    if not archive_path.is_file():
        raise ValueError(f"archive does not exist: {archive_path}")
    policy = load_archive_policy()
    max_files = _policy_int(policy, "max_files", 10000, 1, 100000)
    max_file_bytes = _policy_int(policy, "max_file_bytes", 50_000_000, 1, 2_000_000_000)
    max_total_bytes = _policy_int(policy, "max_total_bytes", 500_000_000, 1, 10_000_000_000)
    issues: list[str] = []
    try:
        with zipfile.ZipFile(archive_path, "r") as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                issues.append("archive contains duplicate member names")
            unsafe = [name for name in names if not _member_is_safe(name)]
            if unsafe:
                issues.append(f"archive contains unsafe member paths: {', '.join(unsafe[:3])}")
            content_infos = [info for info in infos if not info.is_dir() and info.filename != ARCHIVE_MANIFEST]
            if len(content_infos) > max_files:
                issues.append(f"archive content exceeds max_files: {len(content_infos)}")
            oversized = [info.filename for info in content_infos if info.file_size > max_file_bytes]
            if oversized:
                issues.append(f"archive member exceeds max_file_bytes: {oversized[0]}")
            content_bytes = sum(info.file_size for info in content_infos)
            if content_bytes > max_total_bytes:
                issues.append(f"archive content exceeds max_total_bytes: {content_bytes}")
            within_read_budget = len(content_infos) <= max_files and not oversized and content_bytes <= max_total_bytes
            manifest_infos = [info for info in infos if info.filename == ARCHIVE_MANIFEST]
            if len(manifest_infos) != 1:
                issues.append("archive must contain exactly one integrity manifest")
                manifest: object = {}
            elif manifest_infos[0].file_size > 2_000_000:
                issues.append("archive integrity manifest exceeds 2000000 bytes")
                manifest = {}
            else:
                try:
                    manifest = json.loads(bundle.read(manifest_infos[0]).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    issues.append(f"invalid archive integrity manifest: {exc}")
                    manifest = {}

            if not isinstance(manifest, dict):
                issues.append("archive integrity manifest must be a JSON object")
                manifest = {}
            if manifest.get("format") != "haness-frame-archive":
                issues.append("unsupported archive manifest format")
            if manifest.get("format_version") != ARCHIVE_FORMAT_VERSION:
                issues.append("unsupported archive manifest version")
            records = manifest.get("files", [])
            if not isinstance(records, list):
                issues.append("archive manifest files must be a list")
                records = []

            actual = {info.filename: info for info in infos if not info.is_dir() and info.filename != ARCHIVE_MANIFEST}
            expected: dict[str, dict[str, object]] = {}
            for index, record in enumerate(records):
                if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                    issues.append(f"invalid archive manifest file record at index {index}")
                    continue
                path = str(record["path"])
                if not _member_is_safe(path):
                    issues.append(f"unsafe archive manifest file path: {path}")
                if path in expected:
                    issues.append(f"duplicate archive manifest file record: {path}")
                expected[path] = record
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            if missing:
                issues.append(f"archive members missing from ZIP: {', '.join(missing[:3])}")
            if extra:
                issues.append(f"archive members missing from manifest: {', '.join(extra[:3])}")
            for path in sorted(set(actual) & set(expected)):
                info = actual[path]
                record = expected[path]
                if record.get("size") != info.file_size:
                    issues.append(f"archive member size mismatch: {path}")
                    continue
                digest = record.get("sha256")
                if not isinstance(digest, str) or len(digest) != 64:
                    issues.append(f"archive member hash mismatch: {path}")
                elif within_read_budget and _hash_member(bundle, info) != digest.lower():
                    issues.append(f"archive member hash mismatch: {path}")
            if manifest.get("file_count") != len(records):
                issues.append("archive manifest file_count mismatch")
            expected_total = sum(info.file_size for info in actual.values())
            if manifest.get("total_bytes") != expected_total:
                issues.append("archive manifest total_bytes mismatch")
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        issues.append(f"invalid ZIP archive: {exc}")

    report = {
        "valid": not issues,
        "path": str(archive_path),
        "issues": issues,
    }
    mark_check("archive_integrity", not issues, archive_path.name if not issues else "; ".join(issues[:3]))
    log_event("archive.verified", **report)
    return report


def create_archive(label: str = "") -> Path:
    ensure_workspace()
    archive_dir = WORKSPACE / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    policy = load_archive_policy()
    files = _archive_files(policy)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.strip())[:48]
    name = f"{ROOT.name}-{stamp}{('-' + safe_label) if safe_label else ''}.zip"
    archive_path = archive_dir / name
    max_file_bytes = _policy_int(policy, "max_file_bytes", 50_000_000, 1, 2_000_000_000)
    max_total_bytes = _policy_int(policy, "max_total_bytes", 500_000_000, 1, 10_000_000_000)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for item, rel in files:
                bundle.write(item, arcname=f"{ROOT.name}/{rel.as_posix()}")
        with zipfile.ZipFile(archive_path, "a", compression=zipfile.ZIP_DEFLATED) as bundle:
            manifest = _build_archive_manifest(
                bundle,
                label=label,
                max_file_bytes=max_file_bytes,
                max_total_bytes=max_total_bytes,
            )
            bundle.writestr(ARCHIVE_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    mark_check("archive", True, archive_path.name)
    log_event("archive.created", path=str(archive_path), label=label)
    return archive_path
