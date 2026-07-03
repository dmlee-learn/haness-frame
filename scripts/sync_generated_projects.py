from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
TEMPLATE_RUNTIME = ROOT / "src" / "haness_frame_app" / "templates" / "runtime"
RUNTIME_FILES = [path.name for path in TEMPLATE_RUNTIME.glob("*.py")]
EXTRA_MANIFEST_FILES = [
    "workspace/evidence/search-plan.json",
    "research/search-evidence-draft.md",
    "research/search-evidence-gaps.md",
    "src/harness_app/decision.py",
]
COMMAND_SNIPPETS = [
    "python -m harness_app summary",
    "python -m harness_app search-plan",
    "python -m harness_app evidence-draft",
    "python -m harness_app evidence-gaps",
    "python -m harness_app evidence-commit",
    "python -m harness_app decision-template",
    "python -m harness_app decision-draft",
    "python -m harness_app verify",
]


def copy_runtime(project: Path) -> None:
    dst = project / "src" / "harness_app"
    dst.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        shutil.copy2(TEMPLATE_RUNTIME / name, dst / name)


def update_manifest(project: Path) -> None:
    path = project / "workspace" / "manifest.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", [])
    if not isinstance(files, list):
        files = []
    for rel in EXTRA_MANIFEST_FILES:
        if rel not in files:
            files.append(rel)
    data["files"] = files
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def update_runtime_doc(project: Path) -> None:
    path = project / "docs" / "06-system-runtime.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    updated = text
    for snippet in COMMAND_SNIPPETS:
        if snippet not in updated:
            anchor = "python -m harness_app debate"
            if anchor in updated:
                updated = updated.replace(anchor, f"{snippet}\n{anchor}", 1)
            else:
                updated = updated.rstrip() + f"\n{snippet}\n"
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def ensure_new_files(project: Path) -> None:
    evidence_plan = project / "workspace" / "evidence" / "search-plan.json"
    if not evidence_plan.exists():
        evidence_plan.parent.mkdir(parents=True, exist_ok=True)
        evidence_plan.write_text(json.dumps({"provider": "google", "searches": []}, indent=2, ensure_ascii=False), encoding="utf-8")
    draft = project / "research" / "search-evidence-draft.md"
    if not draft.exists():
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("# Search Evidence Draft\n\nRun `python app.py search-plan` first.\n", encoding="utf-8")
    gaps = project / "research" / "search-evidence-gaps.md"
    if not gaps.exists():
        gaps.parent.mkdir(parents=True, exist_ok=True)
        gaps.write_text("# Search Evidence Gaps\n\nRun `python app.py search-plan` first.\n", encoding="utf-8")


def main() -> int:
    for project in sorted(p for p in PROJECTS.iterdir() if p.is_dir()):
        copy_runtime(project)
        update_manifest(project)
        update_runtime_doc(project)
        ensure_new_files(project)
        print(project.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
