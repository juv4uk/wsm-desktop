# SPDX-License-Identifier: LicenseRef-Volnist
"""The installer executor is preview-only until target-bound APPLY is proven."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import ExecutorError, execute  # noqa: E402
from wsm_install.install_steps import Step  # noqa: E402

DISK = "/dev/nvme0n1"
STEPS = [
    Step(
        ["/run/current-system/profile/sbin/partprobe", DISK],
        "re-read the requested partition table",
    ),
    Step(
        [
            "/run/current-system/profile/sbin/mkfs.ext4",
            "-F",
            "/dev/nvme0n1p2",
        ],
        "format root",
        destructive=True,
    ),
    Step(
        [
            "/run/current-system/profile/bin/mount",
            "/dev/nvme0n1p2",
            "/mnt",
        ],
        "mount root",
    ),
]


class DryRunTests(unittest.TestCase):
    def test_preview_never_executes_commands(self) -> None:
        output: list[str] = []
        results = execute(STEPS, DISK, out=output.append)
        self.assertEqual(len(results), len(STEPS))
        self.assertTrue(all(result.status == "skipped" for result in results))
        self.assertTrue(all("APPLY disabled" in result.detail for result in results))
        self.assertEqual(len(output), len(STEPS))
        self.assertTrue(all(result.command for result in results))

    def test_preview_is_deterministic_and_marks_destructive_steps(self) -> None:
        first: list[str] = []
        second: list[str] = []
        execute(STEPS, DISK, out=first.append)
        execute(STEPS, DISK, out=second.append)
        self.assertEqual(first, second)
        self.assertIn("[DESTRUCTIVE]", first[1])

    def test_empty_plan_is_an_empty_preview(self) -> None:
        self.assertEqual(execute([], DISK, out=lambda _: None), [])


class ApplyRefusalTests(unittest.TestCase):
    def test_every_non_dry_run_request_is_refused_before_any_output(self) -> None:
        output: list[str] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, DISK, dry_run=False, out=output.append)
        self.assertEqual(caught.exception.code, "execute.apply-disabled")
        self.assertEqual(output, [])

    def test_truthy_non_boolean_dry_run_value_is_not_accepted(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, DISK, dry_run=1, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.apply-disabled")


class InputValidationTests(unittest.TestCase):
    def test_only_allow_list_whole_disk_paths_are_previewed(self) -> None:
        for disk in ("", "/dev/.", "/dev/..", "/dev/nvme0n1p2", "/tmp/disk"):
            with self.subTest(disk=disk), self.assertRaises(ExecutorError) as caught:
                execute(STEPS, disk, out=lambda _: None)
            self.assertEqual(caught.exception.code, "execute.disk-path")

    def test_non_step_values_are_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([{"command": ["mkfs"]}], DISK, out=lambda _: None)  # type: ignore[list-item]
        self.assertEqual(caught.exception.code, "execute.step-type")

    def test_invalid_argv_is_refused(self) -> None:
        invalid = Step(["/bin/echo", "bad" + chr(10) + "argument"], "display")
        with self.assertRaises(ExecutorError) as caught:
            execute([invalid], DISK, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.command")

    def test_preview_rejects_device_operands_outside_the_displayed_target(self) -> None:
        mismatched = Step(
            ["/usr/sbin/mkfs.ext4", "-F", "/dev/sda1"],
            "format a different disk",
            destructive=True,
        )
        with self.assertRaises(ExecutorError) as caught:
            execute([mismatched], DISK, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.target-mismatch")

    def test_preview_accepts_partition_operands_of_the_displayed_nvme_target(self) -> None:
        partition = Step(
            ["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"],
            "format the selected root partition",
            destructive=True,
        )
        self.assertEqual(
            execute([partition], DISK, out=lambda _: None)[0].status,
            "skipped",
        )


if __name__ == "__main__":
    unittest.main()
