# SPDX-License-Identifier: LicenseRef-Volnist
"""The native FPC partition planner must match the Python planner at runtime."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASCAL_DIR = ROOT / "tools" / "pascal"
SRC = PASCAL_DIR / "wsm_partition.pas"
sys.path.insert(0, str(ROOT))

from wsm_install.partition import Disk, plan  # noqa: E402

GIB = 1024 ** 3


class SourceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_all_python_whole_disk_name_families_are_implemented(self) -> None:
        self.assertIn("IsAsciiLowerLetters(Suffix)", self.pas)
        self.assertIn("IsAsciiDigits(Suffix)", self.pas)
        self.assertIn("Base[Index] <> 'n'", self.pas)

    def test_exact_refusal_codes_and_limits_match_python(self) -> None:
        for code in (
            "disk.path", "disk.firmware", "disk.running-system",
            "disk.too-small", "disk.acknowledgement", "disk.size-drift",
        ):
            self.assertIn(code, self.pas)
        self.assertIn("EspMib = 512", self.pas)
        self.assertIn("BiosBootMib = 1", self.pas)
        self.assertIn("MinRootMib = 12 * 1024", self.pas)
        self.assertIn("SizeTolerancePercent = 2", self.pas)

    def test_planner_never_executes_or_writes_commands(self) -> None:
        for forbidden in ("ExecuteProcess", "fpsystem", "fpExec", "popen", "Shell(",
                          "Rewrite(", "fpOpen", "AssignFile"):
            self.assertNotIn(forbidden, self.pas)
        self.assertIn('"executed":false', self.pas)
        self.assertIn('["sgdisk","--zap-all"', self.pas)


@unittest.skipUnless(
    (shutil.which("fpc") and shutil.which("make")) or os.environ.get("WSM_PARTITION_FPC_BINARY"),
    "FPC is not installed; native partition runtime parity is not proven locally",
)
class RuntimePlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("WSM_PARTITION_FPC_BINARY")
        cls.temporary = None
        if supplied:
            candidate = Path(supplied)
            cls.program = candidate if candidate.is_absolute() else ROOT / candidate
            if not cls.program.is_file():
                raise AssertionError(f"FPC partition binary does not exist: {cls.program}")
            return

        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-partition-")
        build_dir = Path(cls.temporary.name) / "build"
        completed = subprocess.run(
            ["make", "-C", str(PASCAL_DIR), f"BUILD_DIR={build_dir}", "wsm-partition"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "FPC partition build failed.\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        cls.program = build_dir / "wsm-partition"
        if not cls.program.is_file():
            raise AssertionError("FPC Makefile did not produce wsm-partition")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.temporary is not None:
            cls.temporary.cleanup()

    def run_planner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.program), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_plan_matches_python(self, path: str, size: int, firmware: str) -> None:
        completed = self.run_planner(
            "--disk", path,
            "--size", str(size),
            "--firmware", firmware,
            "--ack", path,
            "--expected-size", str(size),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        expected = plan(
            Disk(path=path, size_bytes=size),
            firmware,
            acknowledgement=path,
            expected_size_bytes=size,
        )
        self.assertEqual(payload["disk"], expected.disk)
        self.assertEqual(payload["disk_size_bytes"], expected.disk_size_bytes)
        self.assertEqual(payload["partitions"], expected.partitions)
        self.assertEqual(payload["commands"], expected.commands())
        self.assertIs(payload["executed"], False)

    def test_uefi_nvme_layout_and_commands_match_python(self) -> None:
        self.assert_plan_matches_python("/dev/nvme0n1", 256 * GIB, "uefi")

    def test_bios_multi_letter_sd_layout_matches_python(self) -> None:
        self.assert_plan_matches_python("/dev/sdaa", 64 * GIB, "bios")

    def test_multi_letter_virtual_disk_path_matches_python(self) -> None:
        self.assert_plan_matches_python("/dev/vdaa", 32 * GIB, "uefi")

    def test_mmc_block_device_path_matches_python(self) -> None:
        self.assert_plan_matches_python("/dev/mmcblk10", 32 * GIB, "uefi")

    def test_exact_two_percent_size_drift_is_accepted(self) -> None:
        actual, expected = 102 * GIB, 100 * GIB
        completed = self.run_planner(
            "--disk", "/dev/nvme0n1",
            "--size", str(actual),
            "--firmware", "uefi",
            "--ack", "/dev/nvme0n1",
            "--expected-size", str(expected),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIs(json.loads(completed.stdout)["executed"], False)

    def test_partition_target_is_refused(self) -> None:
        completed = self.run_planner(
            "--disk", "/dev/nvme0n1p1", "--size", str(256 * GIB),
            "--firmware", "uefi", "--ack", "/dev/nvme0n1p1",
        )
        self.assertEqual(completed.returncode, 10)
        self.assertIn("refused:disk.path:", completed.stderr)

    def test_malformed_nvme_path_is_refused(self) -> None:
        completed = self.run_planner(
            "--disk", "/dev/nvmen", "--size", str(256 * GIB),
            "--firmware", "uefi", "--ack", "/dev/nvmen",
        )
        self.assertEqual(completed.returncode, 10)
        self.assertIn("refused:disk.path:", completed.stderr)

    def test_mmc_path_without_device_number_is_refused(self) -> None:
        completed = self.run_planner(
            "--disk", "/dev/mmcblk", "--size", str(256 * GIB),
            "--firmware", "uefi", "--ack", "/dev/mmcblk",
        )
        self.assertEqual(completed.returncode, 10)
        self.assertIn("refused:disk.path:", completed.stderr)

    def test_running_system_target_is_refused(self) -> None:
        completed = self.run_planner(
            "--disk", "/dev/nvme0n1", "--size", str(256 * GIB),
            "--firmware", "uefi", "--ack", "/dev/nvme0n1",
            "--holds-running-system",
        )
        self.assertEqual(completed.returncode, 10)
        self.assertIn("refused:disk.running-system:", completed.stderr)

    def test_size_drift_above_two_percent_is_refused(self) -> None:
        completed = self.run_planner(
            "--disk", "/dev/nvme0n1", "--size", str(103 * GIB),
            "--firmware", "uefi", "--ack", "/dev/nvme0n1",
            "--expected-size", str(100 * GIB),
        )
        self.assertEqual(completed.returncode, 10)
        self.assertIn("refused:disk.size-drift:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
