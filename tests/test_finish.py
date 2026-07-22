from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haness_frame_app.templates.runtime import finish


class FinishWorkflowTests(unittest.TestCase):
    def test_rejected_verification_plan_stops_before_execution(self) -> None:
        with (
            patch.object(finish, "verification_plan", return_value={"approved": False, "commands": []}),
            patch.object(finish, "qualification_report") as qualify,
            patch.object(finish, "create_archive") as archive,
        ):
            report = finish.finish_project()

        self.assertEqual(report["status"], "blocked")
        qualify.assert_not_called()
        archive.assert_not_called()

    def test_failed_qualification_does_not_create_archive(self) -> None:
        with (
            patch.object(finish, "verification_plan", return_value={"approved": True, "commands": [{}]}),
            patch.object(
                finish,
                "qualification_report",
                return_value={"status": "blocked", "ready": False, "qualified": False, "issues": ["failed"]},
            ),
            patch.object(finish, "create_archive") as archive,
        ):
            report = finish.finish_project()

        self.assertEqual(report["status"], "blocked")
        archive.assert_not_called()

    def test_completed_finish_qualifies_archives_and_verifies(self) -> None:
        qualification = {
            "status": "qualified",
            "ready": True,
            "qualified": True,
            "issues": [],
            "warnings": ["shared model"],
            "verification": {"passed": True},
        }
        with (
            patch.object(finish, "verification_plan", return_value={"approved": True, "commands": [{}]}),
            patch.object(finish, "qualification_report", return_value=qualification) as qualify,
            patch.object(finish, "create_archive", return_value=Path("workspace/archives/project.zip")) as archive,
            patch.object(finish, "verify_archive", return_value={"valid": True, "issues": []}) as verify,
        ):
            report = finish.finish_project(label="release")

        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["archive"]["valid"])
        qualify.assert_called_once_with(run_verification=True)
        archive.assert_called_once_with("release")
        verify.assert_called_once_with(Path("workspace/archives/project.zip"))


if __name__ == "__main__":
    unittest.main()
