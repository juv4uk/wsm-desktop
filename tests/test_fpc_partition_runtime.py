# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime contract checks for the native FPC partition planner.

The executable emits a plan; it does not run sgdisk or open a block device.
Every successful test uses a synthetic /dev/sdz path and every refusal test
must exit before emitting a plan.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    ROOT / "build" / "fpc" / "wsm_partition",
    ROOT / "build" / "pascal" / "wsm-partition",
)
BINARY = (
    Path(os.environ["WSM_FPC_PARTITION_BINARY"])
    if os.environ.get("WSM_FPC_PARTITION_BINARY")
    else next((candidate for candidate in CANDIDATES if candidate.is_file()), CANDIDATES[0])
)


@unittest.skipUnless(BINARY.is_file(), "the dedicated FPC workflow compiles the partition planner")
class FpcPartitionRuntimeTests(unittest.TestCase):
    def run_planner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(BINARY), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def good_arguments(self, *extra: str) -> tuple[str, ...]:
        return (
            "--disk", "/dev/sdz",
            "--size", "20000000000",
            "--firmware", "uefi",
            "--ack", "/dev/sdz",
            *extra,
        )

    def test_uefi_plan_is_json_and_never_executes_commands(self) -> None:
        result = self.run_planner(*self.good_arguments())
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["executed"])
        self.assertEqual(plan["disk"], "/dev/sdz")
        self.assertEqual(
            [part["typecode"] for part in plan["partitions"]],
            ["ef00", "8300"],
        )
        self.assertEqual(plan["commands"][0], ["sgdisk", "--zap-all", "/dev/sdz"])

    def test_bios_plan_uses_a_grub_boot_partition(self) -> None:
        args = list(self.good_arguments())
        args[args.index("uefi")] = "bios"
        result = self.run_planner(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["executed"])
        self.assertEqual(
            [part["typecode"] for part in plan["partitions"]],
            ["ef02", "8300"],
        )

    def test_partition_paths_are_refused(self) -> None:
        args = list(self.good_arguments())
        args[args.index("--disk") + 1] = "/dev/sdz1"
        args[args.index("--ack") + 1] = "/dev/sdz1"
        result = self.run_planner(*args)
        self.assertEqual(result.returncode, 10)
        self.assertIn("refused:disk.path:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_running_system_disks_are_refused(self) -> None:
        result = self.run_planner(*self.good_arguments(), "--holds-running-system")
        self.assertEqual(result.returncode, 10)
        self.assertIn("refused:disk.running-system:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_acknowledgement_must_match_the_exact_device(self) -> None:
        args = list(self.good_arguments())
        args[args.index("--ack") + 1] = "/dev/sdy"
        result = self.run_planner(*args)
        self.assertEqual(result.returncode, 10)
        self.assertIn("refused:disk.acknowledgement:", result.stderr)
        self.assertEqual(result.stdout, "")
