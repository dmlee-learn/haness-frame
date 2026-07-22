from __future__ import annotations

from pathlib import Path

from .archive import create_archive, verify_archive
from .qualification import qualification_report
from .verification import verification_plan


def finish_project(*, label: str = "") -> dict[str, object]:
    plan = verification_plan()
    report: dict[str, object] = {
        "status": "running",
        "verification_plan": plan,
        "qualification": None,
        "archive": None,
    }
    if not plan.get("approved"):
        report["status"] = "blocked"
        report["next_action"] = "Review rejected verification commands with `python app.py verification-plan`."
        return report

    qualification = qualification_report(run_verification=True)
    report["qualification"] = {
        "status": qualification.get("status", ""),
        "ready": qualification.get("ready", False),
        "qualified": qualification.get("qualified", False),
        "issues": qualification.get("issues", []),
        "warnings": qualification.get("warnings", []),
        "verification": qualification.get("verification", {}),
    }
    if not qualification.get("qualified"):
        report["status"] = "blocked"
        report["next_action"] = "Resolve qualification issues, then run `python app.py finish` again."
        return report

    archive_path = create_archive(label)
    archive_report = verify_archive(archive_path)
    report["archive"] = {
        "path": str(Path(archive_path)),
        "valid": archive_report.get("valid", False),
        "issues": archive_report.get("issues", []),
    }
    report["status"] = "completed" if archive_report.get("valid") else "archive_invalid"
    if report["status"] != "completed":
        report["next_action"] = "Inspect archive issues with `python app.py archive-verify`."
    return report
