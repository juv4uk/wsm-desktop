# SPDX-License-Identifier: LicenseRef-Volnist
"""Pseudo-graphics must be navigable and must never proceed on a wrong answer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.guided import Candidate  # noqa: E402
from wsm_install.tui import box, disk_list, normalize_key, run_tui  # noqa: E402

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


def plan_recorder(calls: list):
    def plan(path, size, firmware):
        calls.append(("plan", path, firmware))

    return plan


def type_path(path: str) -> list[str]:
    return list(path) + ["enter"]


class BoxTests(unittest.TestCase):
    def test_box_is_rectangular(self) -> None:
        lines = box("Title", ["one", "two"])
        widths = {len(line) for line in lines}
        self.assertEqual(len(widths), 1, f"ragged box: {widths}")

    def test_shortcuts_work_with_us_and_ukrainian_layouts(self) -> None:
        self.assertEqual(normalize_key("q"), "quit")
        self.assertEqual(normalize_key("й"), "quit")
        self.assertEqual(normalize_key("j"), "down")
        self.assertEqual(normalize_key("о"), "down")
        self.assertEqual(normalize_key("k"), "up")
        self.assertEqual(normalize_key("л"), "up")
        self.assertEqual(normalize_key("\r"), "enter")

    def test_box_has_borders_and_title(self) -> None:
        lines = box("WSM • перегляд плану", ["body"])
        self.assertTrue(lines[0].startswith("┌") and lines[0].endswith("┐"))
        self.assertIn("WSM • перегляд плану", lines[1])
        self.assertTrue(lines[-1].startswith("└"))

    def test_long_lines_are_truncated_not_wrapped(self) -> None:
        lines = box("T", ["x" * 500])
        self.assertEqual(len({len(line) for line in lines}), 1)

    def test_disk_list_marks_the_selection(self) -> None:
        lines = disk_list(DISKS, 1)
        self.assertTrue(lines[1].startswith(">"))
        self.assertTrue(lines[0].startswith(" "))
        self.assertIn("знімний", lines[1])


class NavigationTests(unittest.TestCase):
    def test_down_moves_the_selection(self) -> None:
        calls: list = []
        screen = FakeScreen(["down", "enter"] + ["enter"] + type_path("/dev/sda") + ["enter"])
        code = run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["plan"])
        self.assertEqual(calls[0][1], "/dev/sda")
        self.assertIn("Застосування вимкнено", screen.text())

    def test_selection_wraps_around(self) -> None:
        calls: list = []
        screen = FakeScreen(["up", "enter"] + ["enter"] + type_path("/dev/sda") + ["enter"])
        run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(calls[0][1], "/dev/sda")

    def test_quit_at_disk_choice_changes_nothing(self) -> None:
        calls: list = []
        screen = FakeScreen(["quit"])
        code = run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_wrong_typed_path_stops_before_planning(self) -> None:
        """The first disk is selected, so typing the second disk's path must fail."""
        calls: list = []
        screen = FakeScreen(["enter"] + ["enter"] + type_path("/dev/sda") + ["enter"])
        code = run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("не збігається", screen.text())

    def test_backspace_corrects_the_typed_path(self) -> None:
        calls: list = []
        # "/dev/sdX" then backspace then "a"
        keys = ["down", "enter", "enter"] + list("/dev/sdX") + ["backspace", "a", "enter", "enter"]
        screen = FakeScreen(keys)
        code = run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(code, 0, screen.text()[-200:])
        self.assertEqual(calls[0][1], "/dev/sda")

    def test_preview_never_calls_an_install_callback(self) -> None:
        calls: list = []
        screen = FakeScreen(["enter", "enter"] + type_path("/dev/nvme0n1"))
        code = run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["plan"])
        self.assertIn("Застосування вимкнено", screen.text())
        self.assertIn("WSM НЕ встановлено", screen.text())

    def test_bios_can_be_selected(self) -> None:
        calls: list = []
        screen = FakeScreen(["enter", "2", "enter"] + type_path("/dev/nvme0n1") + ["enter"])
        run_tui(screen, DISKS, plan_recorder(calls))
        self.assertEqual(calls[0][2], "bios")

    def test_no_disks_shows_a_message_and_quits(self) -> None:
        screen = FakeScreen(["q"])
        code = run_tui(screen, [], plan_recorder([]))
        self.assertEqual(code, 1)
        self.assertIn("Дисків для перегляду", screen.text())


if __name__ == "__main__":
    unittest.main()
