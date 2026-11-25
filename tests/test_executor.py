# SPDX-License-Identifier: LicenseRef-Volnist
"""The executor must remain dry-run-only until target-bound authorization exists."""

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


class DryRunTests(unittest.TestCase):
    def test_default_mode_executes_nothing_and_marks_every_step_skipped(self) -> None:
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", out=output.append)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.status == "skipped" for result in results))
        self.assertTrue(all(result.detail.startswith("dry run") for result in results))
        self.assertIn("dry-run target: /dev/nvme0n1", output[0])
        self.assertTrue(any("[DESTRUCTIVE] would run:" in line for line in output))

    def test_explicit_dry_run_is_still_data_only(self) -> None:
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertEqual([result.command for result in results], [step.command for step in STEPS])
        self.assertEqual([result.destructive for result in results], [False, True, False])

    def test_real_execution_is_refused_even_with_a_disk_name(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", dry_run=False, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.real-mode-disabled")
        self.assertIn("target binding", caught.exception.message)

    def test_non_boolean_dry_run_value_fails_closed(self) -> None:
        with self.assertRaises(ExecutorError):
            execute(STEPS, "/dev/nvme0n1", dry_run=1, out=lambda _: None)  # type: ignore[arg-type]

    def test_empty_plan_is_a_valid_preview_but_not_authority_to_write(self) -> None:
        self.assertEqual(execute([], "/dev/nvme0n1", out=lambda _: None), [])
        with self.assertRaises(ExecutorError):
            execute([], "/dev/nvme0n1", dry_run=False, out=lambda _: None)


if __name__ == "__main__":
    unittest.main()
