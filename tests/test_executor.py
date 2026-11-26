# SPDX-License-Identifier: LicenseRef-Volnist
"""The shared executor must be a preview renderer, never a disk writer."""

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
    Step(["/run/current-system/profile/sbin/partprobe", DISK], "re-read"),
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
    def test_default_mode_returns_only_skipped_preview_steps(self) -> None:
        output: list[str] = []
        results = execute(STEPS, DISK, out=output.append)
        self.assertEqual(len(results), len(STEPS))
        self.assertTrue(all(result.status == "skipped" for result in results))
        self.assertTrue(all("command not executed" in result.detail for result in results))
        self.assertIn("Preview context only", output[0])
        self.assertIn("[DESTRUCTIVE]", output[2])

    def test_preview_results_are_immutable_and_render_as_json_lists(self) -> None:
        results = execute(STEPS, DISK, out=lambda _: None)
        self.assertIsInstance(results[0].command, tuple)
        self.assertEqual(results[1].as_dict()["command"], list(STEPS[1].command))
        with self.assertRaises(Exception):
            results[0].status = "done"  # type: ignore[misc]

    def test_real_mode_is_refused_before_output(self) -> None:
        output: list[str] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, DISK, dry_run=False, out=output.append)
        self.assertEqual(caught.exception.code, "execute.apply-disabled")
        self.assertEqual(output, [])

    def test_truthy_non_boolean_is_not_accepted_as_dry_run(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, DISK, dry_run=1, out=lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "execute.apply-disabled")

    def test_only_whole_device_preview_target_is_accepted(self) -> None:
        for target in ("", "/dev/.", "/dev/..", "/dev/nvme0n1p2", "/tmp/disk"):
            with self.subTest(target=target), self.assertRaises(ExecutorError):
                execute(STEPS, target, out=lambda _: None)

    def test_other_device_operand_is_refused_even_in_preview(self) -> None:
        wrong = [Step(
            ["/run/current-system/profile/sbin/mkfs.ext4", "-F", "/dev/sda2"],
            "format another disk",
            destructive=True,
        )]
        with self.assertRaises(ExecutorError) as caught:
            execute(wrong, DISK, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.target-mismatch")

    def test_invalid_step_and_control_character_are_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute([{"command": ["mkfs"]}], DISK, out=lambda _: None)  # type: ignore[list-item]
        self.assertEqual(caught.exception.code, "execute.step-type")
        invalid = Step(["/bin/echo", "bad\nargument"], "display")
        with self.assertRaises(ExecutorError) as caught:
            execute([invalid], DISK, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.command")

    def test_empty_preview_is_allowed_but_not_authority_to_write(self) -> None:
        self.assertEqual(execute([], DISK, out=lambda _: None), [])
        with self.assertRaises(ExecutorError):
            execute([], DISK, dry_run=False, out=lambda _: None)


if __name__ == "__main__":
    unittest.main()
