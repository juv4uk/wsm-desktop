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
    """Package builds and NAR export stay disabled until issue #367 is resolved."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_workflow_is_manual_only(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})

    def test_package_job_is_explicitly_disabled(self) -> None:
        self.assertEqual(self.workflow["jobs"]["archive"]["if"], "${{ false }}")

    def test_no_build_export_or_downloadable_artifact_exists(self) -> None:
        for forbidden in (
            "guix build wsm-tools",
            "guix archive --export",
            "actions/upload-artifact",
            "gh release upload",
            "actions/deploy-pages",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_workflow_records_the_licensing_gate(self) -> None:
        self.assertIn("#367", self.text)
        self.assertIn("розповсюдження", self.text.lower())


class HardwareBuildEvidenceTests(unittest.TestCase):
    """Building is allowed while #367 is open; retaining/distributing a NAR is not."""

    WORKFLOW = ROOT / ".github" / "workflows" / "hw-build-evidence.yml"

    def text(self) -> str:
        return self.WORKFLOW.read_text(encoding="utf-8")

    def test_it_never_retains_or_uploads_a_nar_file(self) -> None:
        text = self.text()
        self.assertIn("guix time-machine -C channels.lock.scm", text)
        for forbidden in (
            "guix archive --export \"$store_path\" > ",
            "actions/upload-artifact",
            "gh release upload",
            "actions/deploy-pages",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_it_records_the_size_that_decides_later_publishing(self) -> None:
        """The nar size is the arithmetic a publishing decision needs."""
        self.assertIn("nar size (bytes)", self.text())
        self.assertIn("archive --export", self.text())
        self.assertIn("PACKAGES: ${{ inputs.packages }}", self.text())
        self.assertIn('for package in "${packages[@]}"', self.text())
        self.assertIn("package list must be a single line", self.text())
        self.assertIn('""|-*', self.text())
        self.assertNotIn("for package in ${{ inputs.packages }}", self.text())

    def test_it_says_in_the_summary_that_nothing_was_published(self) -> None:
        self.assertIn("NAR stream counted and discarded", self.text())

    def test_a_failing_package_fails_the_run(self) -> None:
        text = self.text()
        self.assertIn("failures=$((failures + 1))", text)
        self.assertIn('exit 1', text)

    def test_failure_reporter_uses_summary_not_github_write_api(self) -> None:
        text = self.text()
        self.assertIn("GITHUB_STEP_SUMMARY", text)
        self.assertNotIn("gh api", text)
        self.assertNotIn("GH_TOKEN:", text)

    def test_it_is_manual_only_and_needs_no_approval_phrase(self) -> None:
        """Building locally is not distribution, so it does not need the owner gate."""
        text = self.text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("owner_approval", text)

if __name__ == "__main__":
    unittest.main()
