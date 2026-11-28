# SPDX-License-Identifier: LicenseRef-Volnist
"""The shared executor is preview-only until target binding and consent exist."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSFS = Path("/sys/class/block")
sys.path.insert(0, str(ROOT))

from wsm_install.executor import (  # noqa: E402
    ExecutorError,
    admissible_executable,
    execute,
)
from wsm_install.install_steps import TRUSTED_TOOLS, Step  # noqa: E402
import importlib.util  # noqa: E402
import tempfile  # noqa: E402

from wsm_install.admission import admit  # noqa: E402
from wsm_install.observers import FilesystemObserver, SysfsDiskObserver  # noqa: E402
from wsm_install.tools import is_admissible_path, resolve  # noqa: E402
from wsm_install.tool_map import TOOLS, EXECUTABLES, package  # noqa: E402
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

    def test_missing_partition_inventory_is_unverified_not_failed(self) -> None:
        class UnknownPartitionObserver(FakeObserver):
            def partitioned_disks(self) -> tuple[str, ...] | None:
                return None

        step = Step(["/usr/sbin/sgdisk", "-n", "1:0:+512M", "/dev/nvme0n1"], "partition")
        result = verify_step(step, UnknownPartitionObserver())
        self.assertEqual(result.status, "unverified")
        self.assertIn("inventory is unavailable", result.detail)

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
        partitions: tuple[str, ...] | None = ("/dev/nvme0n1p1", "/dev/nvme0n1p2"),
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

    def partitions(self, path: str) -> tuple[str, ...] | None:
        return self._partitions

    def live_device(self) -> str | None:
        return self._live


class DiskIdentityTests(unittest.TestCase):
    """The target is re-identified immediately before the first write."""

    def test_an_unchanged_disk_passes(self) -> None:
        observer = FakeDiskObserver()
        require_unchanged(capture(observer, "/dev/nvme0n1"), observer)

    def test_unreadable_partition_topology_is_refused(self) -> None:
        with self.assertRaises(IdentityError) as caught:
            capture(FakeDiskObserver(partitions=None), "/dev/nvme0n1")
        self.assertEqual(caught.exception.code, "identity.missing")
        self.assertIn("partition topology", caught.exception.message)

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


class AdmissionChainTests(unittest.TestCase):
    """identity -> admissibility -> consent -> postcondition, reported not applied."""

    PLAN = [
        Step(["/usr/sbin/sgdisk", "-n", "2:0:+64G", "/dev/nvme0n1"], "partition", destructive=True),
        Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
        Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
    ]

    def _identity(self) -> DiskIdentity:
        return capture(FakeDiskObserver(), "/dev/nvme0n1")

    def _report(self, steps=None, *, consent=True, disk_observer=None, observer=None, expected=None):
        return admit(
            steps or self.PLAN,
            "/dev/nvme0n1",
            expected_identity=expected or self._identity(),
            disk_observer=disk_observer or FakeDiskObserver(),
            observer=observer or FakeObserver(),
            consent_for=(lambda index, step, digest: consent),
        )

    def test_a_fully_approved_plan_is_admitted(self) -> None:
        report = self._report()
        self.assertEqual(report.status, "admitted", report.reason)
        self.assertEqual(len(report.plan_digest), 64)
        self.assertTrue(all(step.status == "admitted" for step in report.steps))

    def test_refused_consent_blocks_only_the_destructive_step(self) -> None:
        report = self._report(consent=False)
        self.assertEqual(report.status, "refused")
        self.assertEqual([step.status for step in report.steps], ["refused", "refused", "admitted"])
        self.assertIn("consent.missing", report.steps[0].reason)

    def test_an_inadmissible_command_is_refused_before_consent_is_asked(self) -> None:
        asked: list[int] = []
        plan = [Step(["/bin/sh", "-c", "true"], "untrusted", destructive=True)]
        report = admit(
            plan,
            "/dev/nvme0n1",
            expected_identity=self._identity(),
            disk_observer=FakeDiskObserver(),
            observer=FakeObserver(),
            consent_for=lambda index, step, digest: asked.append(index) or True,
        )
        self.assertEqual(report.status, "refused")
        self.assertIn("inadmissible", report.steps[0].reason)
        self.assertEqual(asked, [], "consent must not be requested for a command that can never run")

    def test_disk_drift_refuses_the_whole_plan(self) -> None:
        drifted = DiskIdentity(
            path="/dev/nvme0n1", major_minor="8:0", size_bytes=500107862016,
            removable=False, partitions=("/dev/nvme0n1p1",),
        )
        report = self._report(expected=drifted)
        self.assertEqual(report.status, "refused")
        self.assertEqual(report.steps, ())
        self.assertIn("identity.drift", report.reason)

    def test_a_failed_postcondition_refuses_the_step(self) -> None:
        report = self._report(observer=FakeObserver(fs="vfat"))
        self.assertEqual(report.status, "refused")
        self.assertIn("failed", report.steps[1].reason)

    def test_a_step_without_a_postcondition_refuses_the_plan(self) -> None:
        plan = [Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read")]
        report = self._report(steps=plan)
        self.assertEqual(report.status, "refused")
        self.assertIn("unverified", report.steps[0].reason)

    def test_every_step_carries_its_digest(self) -> None:
        report = self._report()
        self.assertTrue(all(len(step.step_digest) == 64 for step in report.steps))
        self.assertEqual(len({step.step_digest for step in report.steps}), len(report.steps))


class CoveredStepTests(unittest.TestCase):
    """A stateless step is covered by a later, verified step that reads the device."""

    def _report(self, steps):
        return admit(
            steps,
            "/dev/nvme0n1",
            expected_identity=capture(FakeDiskObserver(), "/dev/nvme0n1"),
            disk_observer=FakeDiskObserver(),
            observer=FakeObserver(),
            consent_for=lambda index, step, digest: True,
        )

    def test_partprobe_is_covered_by_the_step_that_formats_the_partition(self) -> None:
        plan = [
            Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read the table"),
            Step(["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"], "format root", destructive=True),
        ]
        report = self._report(plan)
        self.assertEqual(report.status, "admitted", report.reason)
        self.assertEqual(report.steps[0].status, "admitted-covered")
        self.assertIn("covered by step 2", report.steps[0].reason)

    def test_udevadm_is_covered_by_the_step_that_mounts_the_node(self) -> None:
        plan = [
            Step(["/usr/bin/udevadm", "settle"], "wait for nodes"),
            Step(["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"], "mount root"),
        ]
        report = self._report(plan)
        self.assertEqual(report.status, "admitted", report.reason)
        self.assertEqual(report.steps[0].status, "admitted-covered")

    def test_a_stateless_step_with_no_consumer_stays_refused(self) -> None:
        plan = [Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read the table")]
        report = self._report(plan)
        self.assertEqual(report.status, "refused")
        self.assertEqual(report.steps[0].status, "refused")

    def test_a_consumer_of_another_disk_does_not_cover(self) -> None:
        plan = [
            Step(["/usr/sbin/partprobe", "/dev/nvme0n1"], "re-read the table"),
            Step(["/usr/bin/mount", "/dev/nvme1n1p2", "/mnt"], "mount elsewhere"),
        ]
        report = self._report(plan)
        self.assertEqual(report.steps[0].status, "refused")


def _load_tool_closure_module():
    path = ROOT / "scripts" / "check_tool_closure.py"
    spec = importlib.util.spec_from_file_location("check_tool_closure", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ToolClosureTests(unittest.TestCase):
    """A constant is a claim; this turns it into an observation under a given root."""

    def _run(self, module, argv: list[str]) -> int:
        """Run the CLI without letting its report pollute the test output."""
        import io
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return module.main(argv)

    def _populate(self, root: Path, skip: str | None = None, mode: int = 0o755) -> None:
        for name, path in TRUSTED_TOOLS.items():
            if name == skip:
                continue
            target = root / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(mode)

    def test_a_complete_root_reports_no_problems(self) -> None:
        module = _load_tool_closure_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._populate(root)
            self.assertEqual(module.check(root), [])

    def test_a_missing_tool_is_named(self) -> None:
        module = _load_tool_closure_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._populate(root, skip="sgdisk")
            problems = module.check(root)
            self.assertEqual(len(problems), 1)
            self.assertEqual(problems[0][0], "sgdisk")
            self.assertIn("does not exist", problems[0][1])

    def test_a_missing_tool_names_the_package_the_image_needs(self) -> None:
        """The failure has to say which package to add to the closure, not just what is absent."""
        from wsm_install.tool_map import package

        module = _load_tool_closure_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._populate(root, skip="sgdisk")
            problems = module.check(root)
            self.assertIn(package("sgdisk"), problems[0][1])

    def test_a_non_executable_tool_is_named(self) -> None:
        module = _load_tool_closure_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._populate(root, skip="mount")
            target = root / TRUSTED_TOOLS["mount"].lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("not a program\n", encoding="utf-8")
            target.chmod(0o644)
            problems = module.check(root)
            self.assertEqual([name for name, _ in problems], ["mount"])
            self.assertIn("not executable", problems[0][1])

    def test_the_expected_tools_can_be_listed_without_checking_anything(self) -> None:
        module = _load_tool_closure_module()
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(module.main(["--list"]), 0)
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), len(TRUSTED_TOOLS))

    def test_a_guix_shaped_root_is_checked_against_its_profile(self) -> None:
        """A Guix image has no /usr, so the FHS table must not call it complete."""
        module = _load_tool_closure_module()
        profile = "/run/current-system/profile/bin"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in TRUSTED_TOOLS:
                target = root / profile.lstrip("/") / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#!/bin/sh\n", encoding="utf-8")
                target.chmod(0o755)

            self.assertFalse((root / "usr").exists())
            self.assertEqual(
                len(module.check(root)),
                len(TRUSTED_TOOLS),
                "FHS paths cannot exist in a tree without /usr",
            )
            self.assertEqual(module.check(root, prefixes=(profile,)), [])
            self.assertEqual(self._run(module, ["--root", str(root), "--prefix", profile]), 0)

    def test_prefix_mode_names_a_tool_missing_from_the_profile(self) -> None:
        module = _load_tool_closure_module()
        profile = "/run/current-system/profile/sbin"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in TRUSTED_TOOLS:
                if name == "partprobe":
                    continue
                target = root / profile.lstrip("/") / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#!/bin/sh\n", encoding="utf-8")
                target.chmod(0o755)

            problems = module.check(root, prefixes=(profile,))
            self.assertEqual([name for name, _ in problems], ["partprobe"])
            self.assertIn("not found in any of", problems[0][1])
            self.assertEqual(
                self._run(module, ["--root", str(root), "--prefix", profile]),
                1,
            )

    def test_a_non_directory_root_is_refused_not_reported_complete(self) -> None:
        module = _load_tool_closure_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "a-file"
            root.write_text("not a tree\n", encoding="utf-8")
            self.assertEqual(self._run(module, ["--root", str(root)]), 2)

    def test_the_self_check_passes_and_says_what_it_does_not_prove(self) -> None:
        """The CI gate must be green and must not read as an image closure proof."""
        module = _load_tool_closure_module()
        import io
        from contextlib import redirect_stderr, redirect_stdout

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(module.main(["--self-check"]), 0)
        self.assertIn("self-check OK", out.getvalue())
        self.assertIn("not an image", err.getvalue())

    def test_the_self_check_fails_when_a_tool_is_not_noticed(self) -> None:
        """If the checker stops reporting a problem, the self-check must go red."""
        module = _load_tool_closure_module()
        import io
        from contextlib import redirect_stderr, redirect_stdout

        original = module._problem
        module._problem = lambda name, root, path: []
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(module.main(["--self-check"]), 1)
        finally:
            module._problem = original
        self.assertIn("self-check failed", err.getvalue())

    def test_a_host_root_is_reported_as_the_host_not_an_image(self) -> None:
        module = _load_tool_closure_module()
        self.assertTrue(module.describes_host_root(Path("/")))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(module.describes_host_root(Path(temporary)))

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            # Exit code depends on the runner's own tools; the note must not.
            module.main(["--root", "/"])
        self.assertIn("describes the host", err.getvalue())


class ToolResolutionTests(unittest.TestCase):
    """Tools resolve against explicit prefixes, never against PATH."""

    def test_the_first_prefix_that_has_the_tool_wins(self) -> None:
        found = resolve(
            "sgdisk",
            prefixes=("/run/current-system/profile/sbin", "/usr/sbin"),
            exists=lambda path: path.endswith("sgdisk"),
        )
        self.assertEqual(found, "/run/current-system/profile/sbin/sgdisk")

    def test_a_missing_tool_resolves_to_none(self) -> None:
        self.assertIsNone(resolve("sgdisk", prefixes=("/usr/sbin",), exists=lambda _: False))

    def test_a_bare_name_is_required(self) -> None:
        for bad in ("", "sgdisk ", "/usr/sbin/sgdisk", "sbin/sgdisk"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                resolve(bad, prefixes=("/usr/sbin",), exists=lambda _: True)

    def test_an_untrusted_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            resolve("sh", prefixes=("/usr/bin",), exists=lambda _: True)

    def test_a_path_in_an_allowed_prefix_is_admissible(self) -> None:
        ok, reason = is_admissible_path("/run/current-system/profile/bin/mount")
        self.assertTrue(ok, reason)

    def test_a_trusted_basename_outside_the_prefixes_is_not_admissible(self) -> None:
        ok, reason = is_admissible_path("/tmp/mount")
        self.assertFalse(ok)
        self.assertIn("prefix", reason)

    def test_an_untrusted_basename_in_an_allowed_prefix_is_not_admissible(self) -> None:
        ok, reason = is_admissible_path("/usr/bin/sh")
        self.assertFalse(ok)
        self.assertIn("not a trusted tool", reason)

    def test_traversal_out_of_a_prefix_is_not_admissible(self) -> None:
        ok, reason = is_admissible_path("/usr/sbin/../tmp/sgdisk")
        self.assertFalse(ok)
        self.assertIn("prefix", reason)


class ProfilePathAdmissibilityTests(unittest.TestCase):
    """A Guix image has no /usr, so the same tool must be admissible from a profile."""

    def test_a_profile_resolved_tool_is_admissible(self) -> None:
        admissible, reason = admissible_executable(
            Step(["/run/current-system/profile/sbin/sgdisk", "-p", "/dev/nvme0n1"], "partition")
        )
        self.assertTrue(admissible, reason)

    def test_a_tool_in_a_random_directory_is_still_refused(self) -> None:
        admissible, reason = admissible_executable(Step(["/tmp/sgdisk", "-p", "/dev/nvme0n1"], "partition"))
        self.assertFalse(admissible)
        self.assertIn("not admitted", reason)

    def test_a_traversal_that_lands_back_in_a_prefix_is_refused(self) -> None:
        admissible, reason = admissible_executable(
            Step(["/usr/sbin/../tmp/sgdisk", "-p", "/dev/nvme0n1"], "partition")
        )
        self.assertFalse(admissible)

    def test_an_untrusted_basename_in_a_profile_is_refused(self) -> None:
        admissible, reason = admissible_executable(
            Step(["/run/current-system/profile/bin/sh", "-c", "true"], "shell")
        )
        self.assertFalse(admissible)
        self.assertIn("allowlist", reason)

    def test_the_host_path_from_the_table_still_works(self) -> None:
        admissible, reason = admissible_executable(STEPS[0])
        self.assertTrue(admissible, reason)


class SingleToolMapTests(unittest.TestCase):
    """One logical tool, one path, the same answer in every consumer (#645)."""

    def test_every_consumer_uses_the_same_set(self) -> None:
        from wsm_install.agent import ALLOWED_PROGRAMS
        from wsm_install.executor import ALLOWED_EXECUTABLES
        from wsm_install.install_steps import TRUSTED_TOOLS
        from wsm_install.verify import VERIFIERS

        consumers = {
            "planner": frozenset(TRUSTED_TOOLS.values()),
            "agent": frozenset(ALLOWED_PROGRAMS),
            "executor": frozenset(ALLOWED_EXECUTABLES),
            "verifier": frozenset(VERIFIERS),
        }
        for name, actual in consumers.items():
            with self.subTest(consumer=name):
                self.assertEqual(actual, frozenset(EXECUTABLES), f"{name} drifted from the tool map")

    def test_sgdisk_is_reachable_by_every_consumer(self) -> None:
        from wsm_install.agent import ALLOWED_PROGRAMS
        from wsm_install.executor import ALLOWED_EXECUTABLES
        from wsm_install.verify import VERIFIERS

        path = "/usr/sbin/sgdisk"
        self.assertIn(path, ALLOWED_PROGRAMS)
        self.assertIn(path, ALLOWED_EXECUTABLES)
        self.assertIn(path, VERIFIERS)

    def test_every_tool_names_the_package_that_owns_it(self) -> None:
        for name in TOOLS:
            with self.subTest(tool=name):
                self.assertTrue(package(name).strip(), f"{name} has no owning package")


class SysfsObserverTests(unittest.TestCase):
    """The real observers answer from sysfs and /proc, never from PATH or a command."""

    def _disk(self, root: Path, name: str, *, dev: str = "259:0", sectors: int = 1953525168,
              removable: str = "0", parts: tuple[str, ...] = ("nvme0n1p1", "nvme0n1p2")) -> None:
        block = root / "class" / "block" / name
        block.mkdir(parents=True)
        (block / "dev").write_text(dev + "\n", encoding="utf-8")
        (block / "size").write_text(str(sectors) + "\n", encoding="utf-8")
        (block / "removable").write_text(removable + "\n", encoding="utf-8")
        for number, part in enumerate(parts, start=1):
            partition = block / part
            partition.mkdir()
            (partition / "partition").write_text(f"{number}\n", encoding="utf-8")

    def test_identity_is_read_from_sysfs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._disk(root, "nvme0n1", sectors=1000, removable="1")
            observer = SysfsDiskObserver(sys_root=root)
            identity = observer.block_identity("/dev/nvme0n1")
            self.assertEqual(identity["major_minor"], "259:0")
            self.assertEqual(identity["size_bytes"], 1000 * 512)
            self.assertIs(identity["removable"], True)

    def test_an_unknown_device_is_none_not_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(SysfsDiskObserver(sys_root=Path(temporary)).block_identity("/dev/nope"))

    def test_noncanonical_paths_do_not_alias_a_sysfs_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._disk(root, "sda")
            observer = SysfsDiskObserver(sys_root=root)
            for path in ("sda", "/tmp/sda", "/dev/disk/by-id/sda", "/dev/../sda"):
                with self.subTest(path=path):
                    self.assertIsNone(observer.block_identity(path))

    def test_a_partition_node_is_not_accepted_as_a_whole_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partition = root / "class" / "block" / "sda1"
            partition.mkdir(parents=True)
            (partition / "partition").write_text("1\n", encoding="utf-8")
            (partition / "dev").write_text("8:1\n", encoding="utf-8")
            (partition / "size").write_text("100\n", encoding="utf-8")
            (partition / "removable").write_text("0\n", encoding="utf-8")
            observer = SysfsDiskObserver(sys_root=root)
            self.assertIsNone(observer.block_identity("/dev/sda1"))

    def test_only_sysfs_partition_entries_are_listed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._disk(root, "sda", parts=("sda1", "sda2"))
            # A separate disk name sharing the prefix is not a partition of sda.
            (root / "class" / "block" / "sda" / "sdaa").mkdir()
            observer = SysfsDiskObserver(sys_root=root)
            self.assertEqual(observer.partitions("/dev/sda"), ("/dev/sda1", "/dev/sda2"))

    def test_unreadable_partition_marker_makes_topology_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._disk(root, "sda", parts=())
            partition = root / "class" / "block" / "sda" / "sda1"
            partition.mkdir()
            (partition / "partition").write_text("not-a-number\n", encoding="utf-8")
            observer = SysfsDiskObserver(sys_root=root)
            self.assertIsNone(observer.partitions("/dev/sda"))

    def test_the_live_device_comes_from_the_root_mount(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mounts = Path(temporary) / "mounts"
            mounts.write_text(
                "/dev/sdb1 / ext4 rw 0 0\n/dev/sda2 /mnt ext4 rw 0 0\n", encoding="utf-8"
            )
            self.assertEqual(SysfsDiskObserver(mounts=mounts).live_device(), "/dev/sdb1")

    def test_a_non_device_root_reports_none_rather_than_a_guess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mounts = Path(temporary) / "mounts"
            mounts.write_text("overlay / overlay rw 0 0\n", encoding="utf-8")
            self.assertIsNone(SysfsDiskObserver(mounts=mounts).live_device())

    def test_the_filesystem_observer_refuses_to_guess_a_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            mounts = Path(temporary) / "mounts"
            mounts.write_text("/dev/sda1 /mnt ext4 rw 0 0\n", encoding="utf-8")
            observer = FilesystemObserver(mounts=mounts)
            self.assertIsNone(observer.filesystem_of("/dev/sda1"))
            self.assertTrue(observer.is_mounted("/mnt"))
            self.assertFalse(observer.is_mounted("/elsewhere"))
            self.assertIsNone(observer.partitioned_disks())

    def test_partition_table_verifier_treats_unavailable_inventory_as_unverified(self) -> None:
        step = Step(["/usr/sbin/sgdisk", "-n", "1:0:+512M", "/dev/sda"], "partition")
        result = verify_step(step, FilesystemObserver())
        self.assertEqual(result.status, "unverified")
        self.assertIn("inventory is unavailable", result.detail)


class RealSysfsObserverTests(unittest.TestCase):
    """The observers must distinguish 'nothing there' from 'cannot read it'.

    Two mistakes are easy to make and were both made in this module's first version:
    matching partition names by prefix (so `sdaa` looked like a child of `sda`), and
    returning an empty tuple when sysfs could not be read, which reads as a real
    answer. These tests pin the difference. They skip where the host has no sysfs
    rather than asserting something about the machine they happen to run on.
    """

    def test_an_unknown_device_is_none_and_not_an_empty_inventory(self) -> None:
        observer = SysfsDiskObserver()
        self.assertIsNone(observer.block_identity("/dev/definitely-not-a-device"))
        self.assertIsNone(observer.partitions("/dev/definitely-not-a-device"))

    def test_a_partition_path_is_not_accepted_as_a_whole_disk(self) -> None:
        observer = SysfsDiskObserver()
        self.assertIsNone(observer.block_identity("/dev/definitely-not-a-device1"))

    def test_unreadable_topology_is_none_rather_than_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            block = root / "class" / "block" / "sda"
            block.mkdir(parents=True)
            (block / "dev").write_text("8:0\n", encoding="utf-8")
            (block / "size").write_text("100\n", encoding="utf-8")
            (block / "removable").write_text("0\n", encoding="utf-8")
            (block / "sda1").mkdir()
            block.chmod(0o000)
            try:
                self.assertIsNone(SysfsDiskObserver(sys_root=root).partitions("/dev/sda"))
            finally:
                block.chmod(0o755)

    @unittest.skipUnless(SYSFS.is_dir(), "no sysfs on this host")
    def test_real_partitions_are_listed_without_prefix_matching(self) -> None:
        observer = SysfsDiskObserver()
        for entry in sorted(SYSFS.iterdir()):
            if (entry / "partition").is_file():
                continue
            children = tuple(
                child.name for child in entry.iterdir()
                if child.is_dir() and child.name != entry.name
            )
            if not children:
                continue
            listed = observer.partitions(f"/dev/{entry.name}")
            self.assertIsNotNone(listed, f"{entry.name} has children but reported None")
            self.assertEqual(sorted(listed), sorted(f"/dev/{child}" for child in children))
            return
        self.skipTest("no disk with partitions on this host")


if __name__ == "__main__":
    unittest.main()
