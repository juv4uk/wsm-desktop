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
from wsm_install.install_steps import TRUSTED_TOOLS, Step  # noqa: E402
from wsm_install.plan import PlanDigestError, plan_digest, step_digest  # noqa: E402
from wsm_install.verify import VERIFIERS, verify_step  # noqa: E402

STEPS = [
    Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read"),
    Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
    Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
]


class FakeObserver:
    """Read-only observations the verifier is allowed to consult."""

    def __init__(self, fs: str | None = "ext4", mounted: bool = True, disks: tuple[str, ...] = ("/dev/nvme0n1",)) -> None:
        self._fs = fs
        self._mounted = mounted
        self._disks = disks

    def filesystem_of(self, path: str) -> str | None:
        return self._fs

    def is_mounted(self, path: str) -> bool:
        return self._mounted

    def partitioned_disks(self) -> tuple[str, ...]:
        return self._disks

    def path_exists(self, path: str) -> bool:
        return True


class ExplodingObserver(FakeObserver):
    """Every observation fails; the verifier must report that, not crash or guess."""

    def filesystem_of(self, path: str) -> str | None:
        raise OSError("udev is not answering")

    def is_mounted(self, path: str) -> bool:
        raise OSError("udev is not answering")


class DryRunTests(unittest.TestCase):
    def test_dry_run_returns_not_run_results_and_prints_intent_only(self) -> None:
        output: list[str] = []
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=output.append)
        self.assertEqual(len(results), len(STEPS))
        self.assertTrue(all(result.status == "not-run" for result in results))
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
        self.assertEqual(results[0].status, "not-run")
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
        self.assertEqual(results[0].status, "not-run")

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


class VerifierContractTests(unittest.TestCase):
    """Every allowlisted step has a real postcondition; anything else is unverified.

    The executor on main is preview-only, so this contract is the piece that has to
    exist before APPLY can be re-enabled (#280, acceptance criterion 5). The point
    is the fail-closed direction: an unknown command must never be reported as
    success just because no verifier noticed it.
    """

    def test_unknown_command_is_unverified_not_success(self) -> None:
        result = verify_step(
            Step(["/bin/sh", "-c", "touch /tmp/x"], "untrusted"),
            FakeObserver(),
        )
        self.assertEqual(result.status, "unverified")
        self.assertIn("no postcondition", result.detail)

    def test_relative_executable_is_unverified(self) -> None:
        result = verify_step(Step(["mkfs.ext4", "/dev/nvme0n1p2"], "bare name"), FakeObserver())
        self.assertEqual(result.status, "unverified")

    def test_mkfs_is_verified_only_when_the_filesystem_matches(self) -> None:
        step = Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root")
        self.assertEqual(verify_step(step, FakeObserver(fs="ext4")).status, "verified")
        failed = verify_step(step, FakeObserver(fs="vfat"))
        self.assertEqual(failed.status, "failed")
        self.assertIn("vfat", failed.detail)

    def test_mkfs_without_a_readable_filesystem_is_unverified(self) -> None:
        step = Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root")
        self.assertEqual(verify_step(step, FakeObserver(fs=None)).status, "unverified")

    def test_observer_failure_is_unverified_not_a_crash(self) -> None:
        step = Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root")
        self.assertEqual(verify_step(step, ExplodingObserver()).status, "unverified")

    def test_mount_is_verified_only_when_the_mountpoint_is_mounted(self) -> None:
        step = Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root")
        self.assertEqual(verify_step(step, FakeObserver(mounted=True)).status, "verified")
        self.assertEqual(verify_step(step, FakeObserver(mounted=False)).status, "failed")

    def test_partition_table_step_needs_a_matching_disk(self) -> None:
        step = Step(["/usr/sbin/sgdisk", "-n", "1:0:+512M", "/dev/nvme0n1"], "partition")
        self.assertEqual(verify_step(step, FakeObserver(disks=("/dev/nvme0n1",))).status, "verified")
        self.assertEqual(verify_step(step, FakeObserver(disks=("/dev/sda",))).status, "failed")

    def test_every_trusted_tool_has_a_verifier(self) -> None:
        for name, executable in TRUSTED_TOOLS.items():
            with self.subTest(tool=name):
                self.assertIn(
                    executable, VERIFIERS,
                    f"{name} is allowlisted for execution but has no postcondition",
                )


class PlanDigestTests(unittest.TestCase):
    """A digest that consent and journals can quote, and that notices any change."""

    def test_digest_is_stable_and_hex(self) -> None:
        first = plan_digest("/dev/nvme0n1", STEPS)
        second = plan_digest("/dev/nvme0n1", STEPS)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_a_single_argument_change_changes_the_digest(self) -> None:
        altered = list(STEPS)
        altered[1] = Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p3"], "format root", destructive=True)
        self.assertNotEqual(plan_digest("/dev/nvme0n1", STEPS), plan_digest("/dev/nvme0n1", altered))

    def test_the_destructive_flag_is_part_of_the_digest(self) -> None:
        soft = [Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root")]
        hard = [Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root", destructive=True)]
        self.assertNotEqual(plan_digest("/dev/nvme0n1", soft), plan_digest("/dev/nvme0n1", hard))

    def test_the_disk_is_part_of_the_digest(self) -> None:
        self.assertNotEqual(
            plan_digest("/dev/nvme0n1", STEPS), plan_digest("/dev/nvme1n1", STEPS)
        )

    def test_step_order_is_part_of_the_digest(self) -> None:
        self.assertNotEqual(
            plan_digest("/dev/nvme0n1", STEPS), plan_digest("/dev/nvme0n1", list(reversed(STEPS)))
        )

    def test_an_empty_plan_is_refused(self) -> None:
        with self.assertRaises(PlanDigestError) as caught:
            plan_digest("/dev/nvme0n1", [])
        self.assertEqual(caught.exception.code, "plan.empty")

    def test_a_non_step_is_refused(self) -> None:
        with self.assertRaises(PlanDigestError) as caught:
            plan_digest("/dev/nvme0n1", ["/usr/bin/true"])
        self.assertEqual(caught.exception.code, "plan.step-type")

    def test_step_digest_binds_position_and_disk(self) -> None:
        step = STEPS[1]
        self.assertEqual(
            step_digest("/dev/nvme0n1", step, 2), step_digest("/dev/nvme0n1", step, 2)
        )
        self.assertNotEqual(
            step_digest("/dev/nvme0n1", step, 2), step_digest("/dev/nvme0n1", step, 3)
        )
        self.assertNotEqual(
            step_digest("/dev/nvme0n1", step, 2), step_digest("/dev/nvme1n1", step, 2)
        )


if __name__ == "__main__":
    unittest.main()
