# SPDX-License-Identifier: LicenseRef-Volnist
"""The pseudo-graphical frontend is read-only and never reports installation success."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.guided import Candidate  # noqa: E402
from wsm_install.tui import box, disk_list, run_tui  # noqa: E402

GIB = 1024 ** 3
DISKS = [Candidate("/dev/nvme0n1", 256 * GIB, False), Candidate("/dev/sda", 120 * GIB, True)]


class FakeScreen:
    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)
        self.frames: list[list[str]] = []

    def render(self, lines: list[str]) -> None:
        self.frames.append(lines)

    def read_key(self) -> str:
        return self.keys.pop(0) if self.keys else "quit"

    def text(self) -> str:
        return "\n".join("\n".join(frame) for frame in self.frames)


def preview_recorder(calls: list, result: int = 0):
    def preview(path, size, firmware):
        calls.append(("preview", path, size, firmware))
        return result
    return preview


def type_path(path: str) -> list[str]:
    return list(path) + ["enter"]


class BoxTests(unittest.TestCase):
    def test_box_is_rectangular(self) -> None:
        lines = box("Title", ["one", "two"])
        self.assertEqual(len({len(line) for line in lines}), 1)

    def test_box_has_borders_and_title(self) -> None:
        lines = box("WSM preview", ["body"])
        self.assertTrue(lines[0].startswith("┌") and lines[0].endswith("┐"))
        self.assertIn("WSM preview", lines[1])
        self.assertTrue(lines[-1].startswith("└"))

    def test_long_lines_are_truncated_not_wrapped(self) -> None:
        lines = box("T", ["x" * 500])
        self.assertEqual(len({len(line) for line in lines}), 1)

    def test_disk_list_marks_the_selection(self) -> None:
        lines = disk_list(DISKS, 1)
        self.assertTrue(lines[1].startswith(">"))
        self.assertIn("removable", lines[1])


class NavigationTests(unittest.TestCase):
    def test_down_moves_selection_and_only_previews(self) -> None:
        calls: list = []
        screen = FakeScreen(["down", "enter", "enter"] + type_path("/dev/sda") + ["enter"])
        code = run_tui(screen, DISKS, preview_recorder(calls), "synthetic report")
        self.assertEqual(code, 0)
        self.assertEqual([call[0] for call in calls], ["preview"])
        self.assertEqual(calls[0][1], "/dev/sda")
        self.assertIn("APPLY is disabled", screen.text())
        self.assertIn("system is NOT installed", screen.text())
        self.assertNotIn("Installing", screen.text())
        self.assertNotIn("Installation finished", screen.text())

    def test_selection_wraps_around(self) -> None:
        calls: list = []
        screen = FakeScreen(["up", "enter", "enter"] + type_path("/dev/sda") + ["enter"])
        run_tui(screen, DISKS, preview_recorder(calls), "synthetic report")
        self.assertEqual(calls[0][1], "/dev/sda")

    def test_quit_at_disk_choice_changes_nothing(self) -> None:
        calls: list = []
        code = run_tui(FakeScreen(["quit"]), DISKS, preview_recorder(calls))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_wrong_typed_path_stops_before_preview(self) -> None:
        calls: list = []
        screen = FakeScreen(["enter", "enter"] + type_path("/dev/sda") + ["enter"])
        code = run_tui(screen, DISKS, preview_recorder(calls))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("does not match", screen.text())

    def test_backspace_corrects_the_typed_path(self) -> None:
        calls: list = []
        keys = ["down", "enter", "enter"] + list("/dev/sdX") + ["backspace", "a", "enter", "enter"]
        screen = FakeScreen(keys)
        code = run_tui(screen, DISKS, preview_recorder(calls), "report")
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][1], "/dev/sda")

    def test_preview_failure_is_not_reported_as_success(self) -> None:
        calls: list = []
        screen = FakeScreen(["enter", "enter"] + type_path("/dev/nvme0n1") + ["enter"])
        code = run_tui(screen, DISKS, preview_recorder(calls, 2))
        self.assertEqual(code, 2)
        self.assertEqual([call[0] for call in calls], ["preview"])
        self.assertIn("Preview failed", screen.text())
        self.assertNotIn("system is NOT installed", screen.text())

    def test_preview_without_exit_code_is_refused(self) -> None:
        screen = FakeScreen(["enter", "enter"] + type_path("/dev/nvme0n1") + ["enter"])
        code = run_tui(screen, DISKS, lambda *_args: None)
        self.assertEqual(code, 1)
        self.assertIn("Preview callback returned no exit code", screen.text())

    def test_no_disks_shows_message_and_quits(self) -> None:
        screen = FakeScreen(["quit"])
        code = run_tui(screen, [], preview_recorder([]))
        self.assertEqual(code, 1)
        self.assertIn("No whole disks", screen.text())
