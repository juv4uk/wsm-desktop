# SPDX-License-Identifier: LicenseRef-Volnist
"""Environment checks must fail before the first disk is touched, not at step five."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.preflight_env import (  # noqa: E402
    check_guix,
    check_mount_point,
    check_report,
    check_root,
    check_system_file,
    check_tools,
    verdict,
)

SYSTEM = ROOT / "systems" / "desktop.scm"


def which_factory(present: set[str]):
    return lambda name: f"/usr/bin/{name}" if name in present else None


class ToolTests(unittest.TestCase):
    def test_missing_tool_fails_and_names_it(self) -> None:
        result = check_tools(which_factory(set()))
        self.assertEqual(result["status"], "fail")
        self.assertIn("mkfs.ext4", result["detail"])

    def test_all_present_passes(self) -> None:
        from wsm_install.agent import ALLOWED_PROGRAMS

        result = check_tools(which_factory(set(ALLOWED_PROGRAMS)))
        self.assertEqual(result["status"], "pass")

    def test_guix_missing_is_a_failure_not_a_warning(self) -> None:
        """Without guix the disk gets written and the system never built."""
        result = check_guix(which_factory(set()))
        self.assertEqual(result["status"], "fail")
        self.assertIn("guix", result["detail"])


class RootTests(unittest.TestCase):
    def test_non_root_fails(self) -> None:
        self.assertEqual(check_root(lambda: 1000)["status"], "fail")

    def test_root_passes(self) -> None:
        self.assertEqual(check_root(lambda: 0)["status"], "pass")


class MountPointTests(unittest.TestCase):
    def test_missing_mount_point_fails(self) -> None:
        result = check_mount_point(Path("/nonexistent/mnt"), is_mount=lambda _: False)
        self.assertEqual(result["status"], "fail")

    def test_existing_mount_point_fails(self) -> None:
        """Mounting over an existing mount hides the new system."""
        with tempfile.TemporaryDirectory() as temporary:
            result = check_mount_point(Path(temporary), is_mount=lambda _: True)
        self.assertEqual(result["status"], "fail")
        self.assertIn("hidden", result["detail"])

    def test_non_empty_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "leftover").write_text("x", encoding="utf-8")
            result = check_mount_point(path, is_mount=lambda _: False)
        self.assertEqual(result["status"], "fail")
        self.assertIn("not empty", result["detail"])

    def test_empty_directory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = check_mount_point(Path(temporary), is_mount=lambda _: False)
        self.assertEqual(result["status"], "pass")


class SystemFileTests(unittest.TestCase):
    def test_real_system_file_passes(self) -> None:
        self.assertEqual(check_system_file(SYSTEM)["status"], "pass")

    def test_missing_file_fails(self) -> None:
        self.assertEqual(check_system_file(Path("/nonexistent.scm"))["status"], "fail")

    def test_non_guix_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x.scm"
            path.write_text("(hello world)", encoding="utf-8")
            result = check_system_file(path)
        self.assertEqual(result["status"], "fail")
        self.assertIn("Guix system declaration", result["detail"])


class ReportTests(unittest.TestCase):
    def test_absent_report_is_not_run(self) -> None:
        self.assertEqual(check_report(None)["status"], "not-run")

    def test_valid_report_passes(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
        self.assertEqual(check_report(fixture)["status"], "pass")

    def test_broken_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "r.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(check_report(path)["status"], "fail")


class VerdictTests(unittest.TestCase):
    def test_one_not_run_makes_it_incomplete(self) -> None:
        result = verdict([
            {"id": "a", "status": "pass", "detail": ""},
            {"id": "b", "status": "not-run", "detail": ""},
        ])
        self.assertEqual(result["overall"], "incomplete")

    def test_failure_outranks_incomplete(self) -> None:
        result = verdict([
            {"id": "a", "status": "not-run", "detail": ""},
            {"id": "b", "status": "fail", "detail": ""},
        ])
        self.assertEqual(result["overall"], "fail")


if __name__ == "__main__":
    unittest.main()
