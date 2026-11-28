# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC planner must refuse everything the Python planner refuses."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_partition.pas"
PY = ROOT / "wsm_install" / "partition.py"


class RefusalParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")
        self.py = PY.read_text(encoding="utf-8")

    def test_every_refusal_code_exists_in_both(self) -> None:
        for code in ("disk.path", "disk.firmware", "disk.running-system",
                     "disk.too-small", "disk.acknowledgement", "disk.size-drift"):
            self.assertIn(code, self.pas, f"missing refusal in Pascal: {code}")
            self.assertIn(code, self.py, f"missing refusal in Python: {code}")

    def test_the_limits_match(self) -> None:
        self.assertIn("EspMib = 512", self.pas)
        self.assertIn("BiosBootMib = 1", self.pas)
        self.assertIn("MinRootMib = 12 * 1024", self.pas)
        self.assertIn("SizeTolerancePercent = 2", self.pas)

    def test_partition_typecodes_match(self) -> None:
        self.assertIn("'ef02'", self.pas)
        self.assertIn("'ef00'", self.pas)
        self.assertIn("'8300'", self.pas)

    def test_holds_running_system_is_a_refusal(self) -> None:
        self.assertIn("HoldsRunningSystem", self.pas)

    def test_acknowledgement_must_name_the_device(self) -> None:
        self.assertIn("Acknowledgement <> Disk.Path", self.pas)


class PlannerIsNotAnExecutorTests(unittest.TestCase):
    """The whole product promise: this unit plans and stops."""

    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_it_never_shells_out(self) -> None:
        for forbidden in ("ExecuteProcess", "fpsystem", "fpExec", "popen", "Shell("):
            self.assertNotIn(forbidden, self.pas, f"execution path present: {forbidden}")

    def test_it_never_writes_a_device(self) -> None:
        for forbidden in ("Rewrite(", "fpOpen", "AssignFile"):
            self.assertNotIn(forbidden, self.pas, f"write path present: {forbidden}")

    def test_the_output_declares_it_was_not_executed(self) -> None:
        self.assertIn('"executed":false', self.pas)

    def test_commands_are_emitted_as_data(self) -> None:
        self.assertIn('["sgdisk","--zap-all"', self.pas)


class DeviceNameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_a_partition_is_not_a_whole_device(self) -> None:
        """sda1, nvme0n1p1 and mmcblk0p1 must all be rejected."""
        self.assertIn("Length(Base) = 3", self.pas)
        self.assertIn("Pos('p', Base) = 0", self.pas)


if __name__ == "__main__":
    unittest.main()
