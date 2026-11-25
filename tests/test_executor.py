# SPDX-License-Identifier: LicenseRef-Volnist
"""The executor stays dry-run-only until its destructive safety contract is complete."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import ExecutorError, default_verifier, execute  # noqa: E402
from wsm_install.install_steps import Step  # noqa: E402

STEPS = [
    Step(["/run/current-system/profile/sbin/partprobe", "/dev/nvme0n1"], "re-read"),
    Step(["/run/current-system/profile/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
    Step(["/run/current-system/profile/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
]


def ok_runner(calls: list[list[str]]):
    def runner(command):
        calls.append(list(command))
        return subprocess.CompletedProcess(list(command), 0, "", "")

    return runner


class DryRunTests(unittest.TestCase):
    def test_dry_run_executes_neither_runner_nor_verifier(self) -> None:
        calls: list[list[str]] = []
        verified: list[Step] = []

        def verifier(step):
            verified.append(step)
            return True, "synthetic"

        results = execute(
            STEPS,
            "/dev/nvme0n1",
            dry_run=True,
            runner=ok_runner(calls),
            verifier=verifier,
            out=lambda _: None,
        )
        self.assertEqual(calls, [])
        self.assertEqual(verified, [])
        self.assertEqual(len(results), len(STEPS))
        self.assertTrue(all(result.status == "skipped" for result in results))

    def test_dry_run_needs_no_acknowledgement(self) -> None:
        execute(STEPS, "/dev/nvme0n1", dry_run=True, runner=ok_runner([]), out=lambda _: None)


class RefusalTests(unittest.TestCase):
    def test_real_run_without_acknowledgement_is_refused(self) -> None:
        calls: list[list[str]] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(STEPS, "/dev/nvme0n1", dry_run=False, runner=ok_runner(calls), out=lambda _: None)
        self.assertEqual(caught.exception.code, "execute.acknowledgement")
        self.assertEqual(calls, [])

    def test_acknowledgement_for_another_disk_is_refused(self) -> None:
        calls: list[list[str]] = []
        with self.assertRaises(ExecutorError) as caught:
            execute(
                STEPS,
                "/dev/nvme0n1",
                acknowledgement="/dev/sda",
                dry_run=False,
                runner=ok_runner(calls),
                out=lambda _: None,
            )
        self.assertEqual(caught.exception.code, "execute.acknowledgement")
        self.assertEqual(calls, [])

    def test_exact_acknowledgement_still_cannot_enable_apply(self) -> None:
        calls: list[list[str]] = []
        verified: list[Step] = []

        def verifier(step):
            verified.append(step)
            return True, "synthetic"

        with self.assertRaises(ExecutorError) as caught:
            execute(
                STEPS,
                "/dev/nvme0n1",
                acknowledgement="/dev/nvme0n1",
                dry_run=False,
                runner=ok_runner(calls),
                verifier=verifier,
                out=lambda _: None,
            )
        self.assertEqual(caught.exception.code, "execute.not-enabled")
        self.assertEqual(calls, [])
        self.assertEqual(verified, [])

    def test_arbitrary_command_cannot_be_executed_even_with_acknowledgement(self) -> None:
        calls: list[list[str]] = []
        malicious = [Step(["/bin/sh", "-c", "touch /tmp/wsm-should-not-exist"], "arbitrary")]
        with self.assertRaises(ExecutorError) as caught:
            execute(
                malicious,
                "/dev/nvme0n1",
                acknowledgement="/dev/nvme0n1",
                dry_run=False,
                runner=ok_runner(calls),
                out=lambda _: None,
            )
        self.assertEqual(caught.exception.code, "execute.not-enabled")
        self.assertEqual(calls, [])

    def test_plan_without_destructive_steps_is_refused(self) -> None:
        harmless = [Step(["/run/current-system/profile/sbin/partprobe", "/dev/nvme0n1"], "re-read")]
        with self.assertRaises(ExecutorError) as caught:
            execute(
                harmless,
                "/dev/nvme0n1",
                acknowledgement="/dev/nvme0n1",
                dry_run=False,
                runner=ok_runner([]),
                out=lambda _: None,
            )
        self.assertEqual(caught.exception.code, "execute.no-destructive-steps")


class VerifierTests(unittest.TestCase):
    def test_partprobe_is_not_reported_verified_without_partition_node_check(self) -> None:
        ok, detail = default_verifier(STEPS[0])
        self.assertFalse(ok)
        self.assertIn("partition nodes", detail)

    def test_udev_settle_is_not_reported_as_device_verification(self) -> None:
        step = Step(["/run/current-system/profile/bin/udevadm", "settle"], "wait for nodes")
        ok, detail = default_verifier(step)
        self.assertFalse(ok)
        self.assertIn("does not prove", detail)

    def test_unknown_step_has_no_implicit_success_verifier(self) -> None:
        step = Step(["/bin/true"], "unknown operation")
        ok, detail = default_verifier(step)
        self.assertFalse(ok)
        self.assertIn("no verifier", detail)


if __name__ == "__main__":
    unittest.main()
