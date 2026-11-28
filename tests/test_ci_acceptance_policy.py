# SPDX-License-Identifier: LicenseRef-Volnist
"""Hosted CI stays deliberately small; integration acceptance is manual."""

from __future__ import annotations

from pathlib import Path
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
    """The owner allowed publication; these are the limits that still hold."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_the_job_is_not_disabled_any_more(self) -> None:
        self.assertNotEqual(self.workflow["jobs"]["archive"].get("if"), "${{ false }}")

    def test_the_owner_permission_is_recorded_in_the_file(self) -> None:
        self.assertIn("ВЛАСНИК ДАВ ДОЗВІЛ", self.text)

    def test_workflow_is_manual_only(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertNotIn("tags:", self.text)
        self.assertNotIn("branches:", self.text)

    def test_no_signing_key_is_created_or_read_here(self) -> None:
        for forbidden in ("secrets.", "guix archive --generate-key", "signing-key"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_publication_is_limited_to_a_verified_draft(self) -> None:
        self.assertIn("--json isDraft", self.text)
        self.assertIn("refusing: $TAG is not a draft release", self.text)
        self.assertNotIn("gh release create", self.text)
        self.assertNotIn("--draft=false", self.text)

    def test_the_archives_are_built_on_the_release_lock(self) -> None:
        self.assertIn("guix time-machine -C channels.lock.scm", self.text)

    def test_a_package_name_that_is_not_a_name_is_refused(self) -> None:
        self.assertIn("*[!A-Za-z0-9._+-]*", self.text)
        self.assertIn("refusing odd package name", self.text)

if __name__ == "__main__":
    unittest.main()
