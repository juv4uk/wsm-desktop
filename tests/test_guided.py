# SPDX-License-Identifier: LicenseRef-Volnist
"""The guided flow must stop far more often than it proceeds."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.guided import Candidate, list_disks, run_guided  # noqa: E402

GIB = 1024 ** 3
DISKS = [Candidate("/dev/nvme0n1", 256 * GIB, False), Candidate("/dev/sda", 120 * GIB, False)]


class FakeConsole:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.output: list[str] = []

    def write(self, text: str) -> None:
        self.output.append(text)

    def read(self, prompt: str) -> str:
        self.output.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    def text(self) -> str:
        return "".join(self.output)


def plan_recorder(calls: list, status: int = 0):
    def plan(path, size, firmware):
        calls.append(("plan", path, size, firmware))
        return status

    return plan


def install_recorder(calls: list, status: int = 0):
    def install(path, size, firmware):
        calls.append(("install", path, size, firmware))
        return status

    return install


class StopTests(unittest.TestCase):
    def run_flow(self, answers: list[str]):
        calls: list = []
        console = FakeConsole(answers)
        code = run_guided(console, DISKS, plan_recorder(calls), install_recorder(calls))
        return code, console, calls

    def test_enter_at_disk_choice_stops(self) -> None:
        code, console, calls = self.run_flow([""])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("Nothing was changed", console.text())

    def test_unknown_number_stops(self) -> None:
        code, _, calls = self.run_flow(["7"])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_wrong_confirmation_stops_before_planning(self) -> None:
        """A yes/no is not enough: the disk name has to be typed."""
        code, console, calls = self.run_flow(["1", "uefi", "yes"])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("does not match", console.text())

    def test_stop_before_install_leaves_the_disk_untouched(self) -> None:
        code, console, calls = self.run_flow(["1", "uefi", "/dev/nvme0n1", ""])
        self.assertEqual(code, 1)
        self.assertEqual([c[0] for c in calls], ["plan"])
        self.assertIn("Stopped after planning", console.text())

    def test_no_disks_found_stops(self) -> None:
        console = FakeConsole([])
        code = run_guided(console, [], plan_recorder([]), install_recorder([]))
        self.assertEqual(code, 1)
        self.assertIn("No whole disks", console.text())


class SuccessTests(unittest.TestCase):
    def test_full_flow_plans_then_installs_the_chosen_disk(self) -> None:
        calls: list = []
        console = FakeConsole(["2", "uefi", "/dev/sda", "install"])
        code = run_guided(console, DISKS, plan_recorder(calls), install_recorder(calls))
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ["plan", "install"])
        self.assertEqual(calls[0][1], "/dev/sda")

    def test_firmware_defaults_to_uefi(self) -> None:
        calls: list = []
        console = FakeConsole(["1", "", "/dev/nvme0n1", "install"])
        run_guided(console, DISKS, plan_recorder(calls), install_recorder(calls))
        self.assertEqual(calls[0][3], "uefi")

    def test_bios_can_be_chosen(self) -> None:
        calls: list = []
        console = FakeConsole(["1", "bios", "/dev/nvme0n1", "install"])
        run_guided(console, DISKS, plan_recorder(calls), install_recorder(calls))
        self.assertEqual(calls[0][3], "bios")


class CallbackFailureTests(unittest.TestCase):
    def test_plan_failure_stops_before_install_confirmation(self) -> None:
        calls: list = []
        console = FakeConsole(["1", "uefi", "/dev/nvme0n1", "install"])
        code = run_guided(
            console, DISKS, plan_recorder(calls, status=2), install_recorder(calls)
        )
        self.assertEqual(code, 2)
        self.assertEqual([call[0] for call in calls], ["plan"])
        self.assertIn("Planning failed", console.text())
        self.assertNotIn("Install now?", console.text())
        self.assertNotIn("Installation finished", console.text())

    def test_apply_failure_is_not_reported_as_success(self) -> None:
        calls: list = []
        console = FakeConsole(["1", "uefi", "/dev/nvme0n1", "install"])
        code = run_guided(
            console, DISKS, plan_recorder(calls), install_recorder(calls, status=1)
        )
        self.assertEqual(code, 1)
        self.assertEqual([call[0] for call in calls], ["plan", "install"])
        self.assertIn("Installation did not complete", console.text())
        self.assertIn("No successful installation is claimed", console.text())
        self.assertNotIn("Installation finished", console.text())


class DiskListingTests(unittest.TestCase):
    def make_block(self, directory: Path, name: str, sectors: int, removable: str = "0") -> None:
        entry = directory / name
        entry.mkdir()
        (entry / "size").write_text(f"{sectors}\n", encoding="utf-8")
        (entry / "removable").write_text(f"{removable}\n", encoding="utf-8")

    def test_loop_and_ram_devices_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            block = Path(temporary)
            self.make_block(block, "nvme0n1", 500_118_388)
            self.make_block(block, "loop0", 8)
            self.make_block(block, "ram0", 8)
            self.make_block(block, "sda", 234_375_168, removable="1")
            disks = list_disks(block)
        self.assertEqual([d.path for d in disks], ["/dev/nvme0n1", "/dev/sda"])
        self.assertTrue(disks[1].removable)

    def test_size_is_converted_from_sectors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            block = Path(temporary)
            self.make_block(block, "sda", 2_097_152)  # 1 GiB in 512-byte sectors
            disks = list_disks(block)
        self.assertEqual(disks[0].size_bytes, GIB)

    def test_missing_sysfs_yields_nothing(self) -> None:
        self.assertEqual(list_disks(Path("/nonexistent/sys/block")), [])


if __name__ == "__main__":
    unittest.main()
