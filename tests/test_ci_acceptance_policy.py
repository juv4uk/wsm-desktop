# SPDX-License-Identifier: LicenseRef-Volnist
"""Hosted CI stays deliberately small; integration acceptance is manual."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release-minimal-live.yml"
MAKEFILE_PATH = ROOT / "Makefile"


class CiAcceptancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.workflow = yaml.load(cls.workflow_text, Loader=yaml.BaseLoader)

    def test_only_fast_checks_run_in_hosted_ci(self) -> None:
        self.assertEqual(set(self.workflow["jobs"]), {"checks"})
        job = self.workflow["jobs"]["checks"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertLessEqual(int(job["timeout-minutes"]), 10)

    def test_ci_runs_for_main_pushes_and_pull_requests(self) -> None:
        events = self.workflow["on"]
        self.assertEqual(events["push"]["branches"], ["main"])
        self.assertIn("pull_request", events)
        self.assertNotIn("workflow_dispatch", events)
        self.assertNotIn("paths", events["push"])
        self.assertNotIn("paths", events["pull_request"] or {})

    def test_ci_runs_tests_docs_and_channel_policy(self) -> None:
        steps = self.workflow["jobs"]["checks"]["steps"]
        commands = " ".join(step.get("run", "") for step in steps)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", commands)
        self.assertIn("python scripts/check_docs.py", commands)
        self.assertIn("--lock channels.lock.scm --policy free", commands)
        self.assertIn("--lock channels/compatibility.lock.scm --policy compatibility", commands)

    def test_slow_or_environmental_acceptance_is_not_in_hosted_ci(self) -> None:
        forbidden = (
            "qemu-system",
            "qemu-acceptance",
            "grub-mkrescue",
            "apt-get",
            "guix-install.sh",
            "workflow_dispatch",
            "acceptance-gates",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.workflow_text)

    def test_ci_has_read_only_permissions_and_no_secrets(self) -> None:
        self.assertEqual(self.workflow["permissions"]["contents"], "read")
        self.assertNotIn("secrets.", self.workflow_text)

    def test_slow_qemu_checks_remain_available_as_manual_commands(self) -> None:
        makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("qemu-acceptance-manual:", makefile)
        for script in (
            "scripts/ci_qemu_guest_smoke.sh",
            "scripts/ci_qemu_hwcheck_guest.py",
            "scripts/ci_cxl_qemu_guest.py",
        ):
            with self.subTest(script=script):
                self.assertIn(script, makefile)
        aggregate = next(
            line.split(":", 1)[1].split()
            for line in makefile.splitlines()
            if line.startswith("check:")
        )
        self.assertNotIn("qemu-acceptance-manual", aggregate)



class ReleaseAcceptanceTimeoutTests(unittest.TestCase):
    """A hung acceptance step must not be able to eat the whole release budget.

    qemu_boot_smoke.py bounds its own serial read (--timeout-seconds), but the
    release job ceiling is six hours. On 2026-11-28 the RC5 draft sat in "BIOS boot
    acceptance" for hours with no diagnosis: either the kill path did not take
    effect or the runner stopped reporting, and nothing at the workflow level
    bounded the step. The step-level timeout is the fail-closed backstop: the
    release fails with a diagnostic inside the job budget instead of hanging.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.load(
            RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )

    def _steps(self) -> list[dict]:
        jobs = self.workflow["jobs"]
        self.assertIn("build-and-publish", jobs)
        return jobs["build-and-publish"]["steps"]

    def test_release_job_keeps_a_bounded_ceiling(self) -> None:
        job = self.workflow["jobs"]["build-and-publish"]
        self.assertLessEqual(int(job["timeout-minutes"]), 360)

    def test_every_qemu_acceptance_step_bounds_itself(self) -> None:
        qemu_steps = [
            step for step in self._steps()
            if "qemu_boot_smoke.py" in (step.get("run") or "")
        ]
        self.assertTrue(
            qemu_steps,
            "the release workflow no longer runs the QEMU boot smoke; update this test",
        )
        for step in qemu_steps:
            name = step.get("name", "<unnamed>")
            self.assertIn(
                "timeout-minutes", step,
                f"acceptance step {name!r} has no step-level timeout; a hung QEMU "
                "would consume the six-hour job budget",
            )
            self.assertLessEqual(
                int(step["timeout-minutes"]), 15,
                f"acceptance step {name!r} may not wait longer than 15 minutes",
            )

class PackageArchiveWorkflowTests(unittest.TestCase):
    """The first distribution lane follows the accepted ADR 0010 boundaries."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.job = self.workflow["jobs"]["archive"]
        self.steps = self.job["steps"]

    def step(self, name: str) -> dict:
        for item in self.steps:
            if name in item.get("name", ""):
                return item
        raise AssertionError(f"workflow step not found: {name}")

    def test_publication_is_manual_only(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertNotIn("push:", self.text)
        self.assertNotIn("schedule:", self.text)
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/main'")

    def test_only_the_owner_package_is_packed(self) -> None:
        build = self.step("Зібрати власний пакет")["run"]
        self.assertIn("wsm-tools", build)
        self.assertIn("pack --format=tarball", build)
        self.assertIn("-L .", build)
        for forbidden in (
            "linux-libre",
            "mesa",
            "nonguix",
            "nvda-580",
            "linux-firmware",
            "wsm-live-tools",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, build)

    def test_package_selection_is_not_user_controlled_shell_input(self) -> None:
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        self.assertNotIn("for package in $" + "{{", self.text)
        self.assertNotIn("PACKAGES=", self.text)

    def test_guix_pack_uses_the_locked_channel_and_no_signing_key(self) -> None:
        build = self.step("Зібрати власний пакет")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertNotIn("guix archive", self.text)
        self.assertNotIn("signing-key", self.text)
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("secrets.", self.text)

    def test_release_is_created_as_draft_only_and_never_published(self) -> None:
        release = self.step("Створити чернетку релізу")["run"]
        self.assertIn("gh release create", release)
        self.assertIn("--draft", release)
        self.assertIn('test "$IS_DRAFT" = "true"', release)
        self.assertNotIn("--draft=false", self.text)
        self.assertNotIn("gh release edit", self.text)
        self.assertNotIn("--prerelease", self.text)

    def test_archive_and_provenance_are_verified_after_upload(self) -> None:
        release = self.step("Створити чернетку релізу")["run"]
        self.assertIn("gh release download", release)
        self.assertIn("sha256sum -c SHA256SUMS", release)
        self.assertIn("tar -tzf wsm-tools-pack.tar.gz", release)
        self.assertIn("PROVENANCE.txt", self.text)
        self.assertIn("CHANNEL-INPUTS.sha256", self.text)

    def test_failure_is_reported_without_claiming_success(self) -> None:
        failures = [
            item for item in self.steps
            if item.get("if") == "failure()"
            and "commits/$GITHUB_SHA/comments" in item.get("run", "")
        ]
        self.assertEqual(len(failures), 1)




if __name__ == "__main__":
    unittest.main()
