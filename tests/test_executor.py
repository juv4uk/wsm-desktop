# SPDX-License-Identifier: LicenseRef-Volnist
"""The executor is where an installer destroys data, so the tests come first."""

from __future__ import annotations

import subprocess
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


def ok_runner(calls: list[list[str]]):
    def runner(command):
        calls.append(list(command))
        return subprocess.CompletedProcess(list(command), 0, "", "")

    return runner


def ok_verifier(step):
    return True, "verified"


def failing_runner(command):
    return subprocess.CompletedProcess(list(command), 1, "", "boom")


class DryRunTests(unittest.TestCase):
    def test_dry_run_executes_nothing(self) -> None:
        calls: list[list[str]] = []
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, runner=ok_runner(calls), verifier=ok_verifier, out=lambda _: None)
        self.assertEqual(calls, [])
        self.assertTrue(all(r.status == "skipped" for r in results))
        self.assertEqual(len(results), 3)

    def test_dry_run_needs_no_acknowledgement(self) -> None:
        execute(STEPS, "/dev/nvme0n1", dry_run=True, runner=ok_runner([]), verifier=ok_verifier, out=lambda _: None)


class RefusalTests(unittest.TestCase):
    def test_real_run_without_acknowledgement_is_refused(self) -> None:
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", dry_run=False, runner=ok_runner([]), verifier=ok_verifier, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.acknowledgement")

    def test_acknowledgement_for_another_disk_is_refused(self) -> None:
        with self.assertRaises(ExecutorError):
            execute(STEPS, "/dev/nvme0n1", acknowledgement="/dev/sda", dry_run=False,
                    runner=ok_runner([]), verifier=ok_verifier, out=lambda _: None)

    def test_plan_without_destructive_steps_is_refused_for_a_real_run(self) -> None:
        """A "real" run with nothing to destroy means the plan is wrong."""
        harmless = [Step(["/usr/sbin/partprobe", "/dev/x"], "re-read")]
        with self.assertRaises(ExecutorError) as caught:
            execute(harmless, "/dev/x", acknowledgement="/dev/x", dry_run=False,
                    runner=ok_runner([]), verifier=ok_verifier, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.no-destructive-steps")


class ExecutionTests(unittest.TestCase):
    def test_steps_run_in_order(self) -> None:
        calls: list[list[str]] = []
        execute(STEPS, "/dev/nvme0n1", acknowledgement="/dev/nvme0n1", dry_run=False,
                runner=ok_runner(calls), verifier=ok_verifier, out=lambda _: None)
        self.assertEqual([c[0] for c in calls],
                         ["/usr/sbin/partprobe", "/usr/sbin/mkfs.ext4", "/usr/bin/mount"])

    def test_first_failure_stops_everything(self) -> None:
        calls: list[list[str]] = []

        def runner(command):
            calls.append(list(command))
            return subprocess.CompletedProcess(list(command), 1 if "mkfs" in command[0] else 0, "", "boom")

        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", acknowledgement="/dev/nvme0n1", dry_run=False,
                    runner=runner, verifier=ok_verifier, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.step-failed")
        # The mount after the failed format must never have been attempted.
        self.assertFalse(any("mount" in c[0] for c in calls))

    def test_a_step_that_exits_zero_but_did_nothing_is_unverified(self) -> None:
        """Exit codes lie; verification reads the system instead."""
        def verifier(step):
            return (False, "no filesystem found") if "mkfs" in step.command[0] else (True, "ok")

        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", acknowledgement="/dev/nvme0n1", dry_run=False,
                    runner=ok_runner([]), verifier=verifier, out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.step-unverified")

    def test_results_record_what_happened(self) -> None:
        results = execute(STEPS, "/dev/nvme0n1", acknowledgement="/dev/nvme0n1", dry_run=False,
                          runner=ok_runner([]), verifier=ok_verifier, out=lambda _: None)
        self.assertTrue(all(r.status == "done" for r in results))
        self.assertTrue(results[1].destructive)
        self.assertFalse(results[0].destructive)


if __name__ == "__main__":
    unittest.main()
