# SPDX-License-Identifier: LicenseRef-Volnist
"""The shared executor is preview-only until target binding and consent exist."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.executor import (  # noqa: E402
    ExecutorError,
    admissible_executable,
    execute,
)
from wsm_install.install_steps import TRUSTED_TOOLS, Step  # noqa: E402
from wsm_install.disk_identity import (  # noqa: E402
    DiskIdentity,
    IdentityError,
    capture,
    require_unchanged,
)
from wsm_install.consent import (  # noqa: E402
    ConsentError,
    grant_consent,
    needs_consent,
    require_consent,
)
from wsm_install.plan_digest import PlanDigestError, plan_digest, step_digest  # noqa: E402
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


class StepConsentTests(unittest.TestCase):
    """One destructive step, one grant, bound to the plan and the command."""

    def test_only_destructive_steps_need_consent(self) -> None:
        self.assertTrue(needs_consent(STEPS[1]))
        self.assertFalse(needs_consent(STEPS[0]))
        require_consent(None, "/dev/nvme0n1", STEPS, 1)

    def test_a_destructive_step_without_a_grant_is_refused(self) -> None:
        with self.assertRaises(ConsentError) as caught:
            require_consent(None, "/dev/nvme0n1", STEPS, 2)
        self.assertEqual(caught.exception.code, "consent.missing")

    def test_a_refusal_returns_no_grant(self) -> None:
        self.assertIsNone(grant_consent("/dev/nvme0n1", STEPS, 2, approve=False))

    def test_an_approved_grant_authorises_exactly_that_step(self) -> None:
        grant = grant_consent("/dev/nvme0n1", STEPS, 2, approve=True)
        self.assertIsNotNone(grant)
        require_consent(grant, "/dev/nvme0n1", STEPS, 2)

    def test_a_changed_plan_invalidates_the_grant(self) -> None:
        grant = grant_consent("/dev/nvme0n1", STEPS, 2, approve=True)
        longer = list(STEPS) + [Step(["/usr/bin/mkdir", "-p", "/mnt/boot"], "mkdir")]
        with self.assertRaises(ConsentError) as caught:
            require_consent(grant, "/dev/nvme0n1", longer, 2)
        self.assertEqual(caught.exception.code, "consent.stale-plan")

    def test_a_changed_command_invalidates_the_grant(self) -> None:
        grant = grant_consent("/dev/nvme0n1", STEPS, 2, approve=True)
        altered = list(STEPS)
        altered[1] = Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p9"], "format root", destructive=True)
        with self.assertRaises(ConsentError) as caught:
            require_consent(grant, "/dev/nvme0n1", altered, 2)
        self.assertEqual(caught.exception.code, "consent.stale-plan")

    def test_a_grant_does_not_cover_another_position(self) -> None:
        grant = grant_consent("/dev/nvme0n1", STEPS, 2, approve=True)
        other = [Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
                 Step(["/usr/sbin/mkfs.fat", "-F", "32", "/dev/nvme0n1p1"], "format esp", destructive=True)]
        with self.assertRaises(ConsentError) as caught:
            require_consent(grant, "/dev/nvme0n1", other, 2)
        self.assertEqual(caught.exception.code, "consent.stale-plan")

    def test_an_index_outside_the_plan_is_refused(self) -> None:
        with self.assertRaises(ConsentError) as caught:
            grant_consent("/dev/nvme0n1", STEPS, 9, approve=True)
        self.assertEqual(caught.exception.code, "consent.index")


class AdmissibleArgvTests(unittest.TestCase):
    """The executor judges the plan itself instead of trusting the planner."""

    def test_an_allowlisted_absolute_tool_is_admissible(self) -> None:
        admissible, reason = admissible_executable(STEPS[0])
        self.assertTrue(admissible)
        self.assertEqual(reason, "")

    def test_a_bare_name_is_not_admissible(self) -> None:
        admissible, reason = admissible_executable(Step(["mkfs.ext4", "/dev/nvme0n1p2"], "bare"))
        self.assertFalse(admissible)
        self.assertIn("absolute path", reason)

    def test_an_absolute_path_outside_the_allowlist_is_not_admissible(self) -> None:
        admissible, reason = admissible_executable(Step(["/bin/sh", "-c", "true"], "shell"))
        self.assertFalse(admissible)
        self.assertIn("allowlist", reason)

    def test_the_preview_still_renders_an_inadmissible_command(self) -> None:
        output: list[str] = []
        results = execute(
            [Step(["/bin/sh", "-c", "true"], "untrusted")],
            "/dev/nvme0n1",
            dry_run=True,
            out=output.append,
        )
        self.assertEqual(results[0].status, "not-run")
        self.assertFalse(results[0].admissible)
        self.assertTrue(any("/bin/sh" in line for line in output))
        self.assertTrue(any("NOT APPLICABLE" in line for line in output))
        self.assertTrue(any("refused for APPLY" in line for line in output))

    def test_an_allowlisted_plan_reports_every_step_admissible(self) -> None:
        results = execute(STEPS, "/dev/nvme0n1", dry_run=True, out=lambda _: None)
        self.assertTrue(all(result.admissible for result in results))
        self.assertTrue(all(result.inadmissible_reason == "" for result in results))

    def test_the_verdict_is_in_the_serialized_result(self) -> None:
        results = execute(
            [Step(["/usr/bin/true"], "unknown but absolute")],
            "/dev/nvme0n1",
            dry_run=True,
            out=lambda _: None,
        )
        payload = results[0].as_dict()
        self.assertFalse(payload["admissible"])
        self.assertIn("allowlist", payload["inadmissible_reason"])


class FakeDiskObserver:
    def __init__(
        self,
        identity: dict[str, object] | None = None,
        partitions: tuple[str, ...] = ("/dev/nvme0n1p1", "/dev/nvme0n1p2"),
        live: str | None = None,
    ) -> None:
        self.identity = identity if identity is not None else {
            "major_minor": "259:0",
            "size_bytes": 500107862016,
            "removable": False,
        }
        self._partitions = partitions
        self._live = live

    def block_identity(self, path: str) -> dict[str, object] | None:
        return self.identity

    def partitions(self, path: str) -> tuple[str, ...]:
        return self._partitions

    def live_device(self) -> str | None:
        return self._live


class DiskIdentityTests(unittest.TestCase):
    """The target is re-identified immediately before the first write."""

    def test_an_unchanged_disk_passes(self) -> None:
        observer = FakeDiskObserver()
        require_unchanged(capture(observer, "/dev/nvme0n1"), observer)

    def test_a_missing_block_device_is_refused(self) -> None:
        class Missing(FakeDiskObserver):
            def block_identity(self, path: str) -> dict[str, object] | None:
                return None

        with self.assertRaises(IdentityError) as caught:
            capture(Missing(), "/dev/nvme0n1")
        self.assertEqual(caught.exception.code, "identity.missing")

    def test_a_changed_node_is_drift(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/nvme0n1")
        moved = FakeDiskObserver(identity={"major_minor": "8:0", "size_bytes": 500107862016, "removable": False})
        with self.assertRaises(IdentityError) as caught:
            require_unchanged(expected, moved)
        self.assertEqual(caught.exception.code, "identity.drift")
        self.assertIn("259:0", caught.exception.message)

    def test_a_changed_size_is_drift(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/nvme0n1")
        smaller = FakeDiskObserver(identity={"major_minor": "259:0", "size_bytes": 16003253424, "removable": False})
        with self.assertRaises(IdentityError) as caught:
            require_unchanged(expected, smaller)
        self.assertEqual(caught.exception.code, "identity.drift")

    def test_a_changed_removable_flag_is_drift(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/nvme0n1")
        replugged = FakeDiskObserver(identity={"major_minor": "259:0", "size_bytes": 500107862016, "removable": True})
        with self.assertRaises(IdentityError) as caught:
            require_unchanged(expected, replugged)
        self.assertEqual(caught.exception.code, "identity.drift")

    def test_a_changed_topology_is_drift(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/nvme0n1")
        repartitioned = FakeDiskObserver(partitions=("/dev/nvme0n1p1",))
        with self.assertRaises(IdentityError) as caught:
            require_unchanged(expected, repartitioned)
        self.assertEqual(caught.exception.code, "identity.drift")

    def test_the_live_medium_is_refused_with_its_own_code(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/sdb")
        live = FakeDiskObserver(live="/dev/sdb1")
        with self.assertRaises(IdentityError) as caught:
            require_unchanged(expected, live)
        self.assertEqual(caught.exception.code, "identity.live-device")

    def test_a_different_live_medium_does_not_block_the_target(self) -> None:
        expected = capture(FakeDiskObserver(), "/dev/nvme0n1")
        require_unchanged(expected, FakeDiskObserver(live="/dev/sdb1"))


if __name__ == "__main__":
    unittest.main()
