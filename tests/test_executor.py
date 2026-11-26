# SPDX-License-Identifier: LicenseRef-Volnist
"""The preview executor must never become a disk mutation boundary."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import ExecutorError, execute  # noqa: E402
from wsm_install.install_steps import Step  # noqa: E402

STEPS = [
    Step(["/run/current-system/profile/sbin/partprobe", "/dev/nvme0n1"], "re-read"),
    Step(
        ["/run/current-system/profile/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"],
        "format root",
        destructive=True,
    ),
    Step(
        ["/run/current-system/profile/bin/mount", "/dev/nvme0n1p2", "/mnt"],
        "mount root",
    ),
]


class PreviewTests(unittest.TestCase):
    def test_preview_renders_every_step_without_executing_commands(self) -> None:
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=output.append)

        self.assertEqual(len(results), len(STEPS))
        self.assertEqual([item.command for item in results], [step.command for step in STEPS])
        self.assertTrue(all(item.status == "skipped" for item in results))
        self.assertTrue(all("not executed" in item.detail for item in results))
        self.assertTrue(all(result.destructive is step.destructive for result, step in zip(results, STEPS)))
        self.assertEqual(len(output), len(STEPS))
        self.assertTrue(any("DESTRUCTIVE" in line for line in output))

    def test_dry_run_is_the_default_and_needs_no_acknowledgement(self) -> None:
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", out=output.append)
        self.assertEqual(len(results), len(STEPS))
        self.assertEqual(len(output), len(STEPS))

    def test_preview_does_not_need_a_physical_device_or_shell(self) -> None:
        # The only device interaction is string/path validation. A missing
        # device is not opened, stat'ed, probed, mounted, or modified.
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=output.append)
        self.assertEqual(len(results), 3)


class ApplyDisabledTests(unittest.TestCase):
    def test_real_apply_is_refused_before_output_or_external_action(self) -> None:
        output: list[str] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", dry_run=False, out=output.append)
        self.assertEqual(caught.exception.code, "execute.apply-disabled")
        self.assertEqual(output, [])

    def test_only_literal_true_enables_preview(self) -> None:
        for value in (False, None, 0, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(ExecutorError) as caught:
                    execute(STEPS, "/dev/nvme0n1", dry_run=value)  # type: ignore[arg-type]
                self.assertEqual(caught.exception.code, "execute.apply-disabled")


class InputValidationTests(unittest.TestCase):
    def test_non_whole_disk_path_is_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1p2", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.disk-path")

    def test_non_device_path_is_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/tmp/disk.img", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.disk-path")

    def test_non_step_item_is_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([object()], "/dev/nvme0n1", dry_run=True, out=lambda _: None)  # type: ignore[list-item]
        self.assertEqual(caught.exception.code, "execute.step-type")

    def test_empty_argv_is_refused(self) -> None:
        step = Step([], "empty command")  # type: ignore[arg-type]
        with self.assertRaises(ExecutorError) as caught:
            execute([step], "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.command")


if __name__ == "__main__":
    unittest.main()
