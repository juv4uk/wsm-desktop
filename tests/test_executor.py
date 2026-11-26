# SPDX-License-Identifier: LicenseRef-Volnist
"""The shared executor is preview-only until target binding and consent exist."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import ExecutorError, execute  # noqa: E402
from wsm_install.install_steps import Step  # noqa: E402

STEPS = [
    Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read"),
    Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
    Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
]


class DryRunTests(unittest.TestCase):
    def test_dry_run_returns_skipped_results_and_prints_intent_only(self) -> None:
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=output.append)
        self.assertEqual(len(results), len(STEPS))
        self.assertTrue(all(result.status == "skipped" for result in results))
        self.assertTrue(all("not executed" in result.detail for result in results))
        self.assertEqual(len(output), len(STEPS))
        self.assertTrue(any("DESTRUCTIVE" in line for line in output))
        self.assertTrue(any("mkfs.ext4" in line for line in output))

    def test_dry_run_needs_no_disk_acknowledgement(self) -> None:
        execute(STEPS, "/dev/nvme0n1", dry_run=True, out=lambda _: None)

    def test_unknown_command_is_only_rendered_not_executed(self) -> None:
        output: list[str] = []
        arbitrary = [Step(["/bin/sh", "-c", "touch /tmp/not-run"], "untrusted preview")]
        results = execute(arbitrary, "/dev/nvme0n1", dry_run=True, out=output.append)
        self.assertEqual(results[0].status, "skipped")
        self.assertIn("/bin/sh", output[0])


class ApplyRefusalTests(unittest.TestCase):
    def test_any_non_true_dry_run_value_is_refused_before_output(self) -> None:
        for value in (False, None, 0, "false"):
            output: list[str] = []
            with self.subTest(value=value), self.assertRaises(ExecutorError) as caught:
                execute(STEPS, "/dev/nvme0n1", dry_run=value, out=output.append)
            self.assertEqual(caught.exception.code, "execute.apply-disabled")
            self.assertEqual(output, [])

    def test_correct_disk_name_does_not_enable_apply(self) -> None:
        output: list[str] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", dry_run=False, out=output.append)
        self.assertEqual(caught.exception.code, "execute.apply-disabled")
        self.assertEqual(output, [])

    def test_api_has_no_runner_verifier_or_acknowledgement_parameter(self) -> None:
        parameters = set(inspect.signature(execute).parameters)
        self.assertEqual(parameters, {"steps", "disk", "dry_run", "out"})


class PreviewValidationTests(unittest.TestCase):
    def test_partition_device_is_not_a_whole_disk_target(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1p1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.disk-path")

    def test_command_device_must_match_target_disk(self) -> None:
        wrong_device = [Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/sda1"], "format root", destructive=True)]
        with self.assertRaises(ExecutorError) as caught:
            execute(wrong_device, "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.device-mismatch")

    def test_embedded_device_argument_must_match_target_disk(self) -> None:
        wrong_device = [Step(["/usr/bin/tool", "--device=/dev/sda1"], "foreign device")]
        with self.assertRaises(ExecutorError) as caught:
            execute(wrong_device, "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.device-mismatch")

    def test_sata_partition_naming_matches_target_disk(self) -> None:
        sata_step = [Step(["/usr/bin/mount", "/dev/sda1", "/mnt"], "mount root")]
        results = execute(sata_step, "/dev/sda", dry_run=True, out=lambda _: None)
        self.assertEqual(results[0].status, "skipped")

    def test_non_step_item_is_rejected(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(["/bin/true"], "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.step-type")

    def test_empty_command_is_rejected(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([Step([], "empty")], "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.command")

    def test_control_character_in_argument_is_rejected(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([Step(["/bin/echo", "bad\nargument"], "bad arg")],
                    "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.command")

    def test_empty_purpose_is_rejected(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([Step(["/bin/true"], " ")], "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.purpose")


if __name__ == "__main__":
    unittest.main()
