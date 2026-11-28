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
    """The owner-authorized WSM pack is manual, bounded and license-preserving."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_the_job_is_enabled_and_owner_permission_is_recorded(self) -> None:
        self.assertNotEqual(self.workflow["jobs"]["archive"].get("if"), "${{ false }}")
        self.assertIn("ВЛАСНИК ДАВ ДОЗВІЛ", self.text)

    def test_workflow_is_manual_only_and_targets_main(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(self.workflow["jobs"]["archive"]["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_permissions_are_scoped_to_pack_attestation_and_release(self) -> None:
        self.assertEqual(
            self.workflow["permissions"],
            {
                "contents": "write",
                "attestations": "write",
                "id-token": "write",
                "artifact-metadata": "write",
            },
        )

    def test_build_uses_the_pinned_channel_and_fixed_wsm_package(self) -> None:
        build = next(
            step for step in self.workflow["jobs"]["archive"]["steps"]
            if step.get("name") == "Evaluate and build the WSM package pack on the locked Guix"
        )["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("(wsm packages wsm)", build)
        self.assertIn("wsm-tools", build)
        self.assertIn("--format=tarball -C gzip", build)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)

    def test_exact_license_provenance_checksums_and_attestation_are_included(self) -> None:
        build = next(
            step for step in self.workflow["jobs"]["archive"]["steps"]
            if step.get("name") == "Evaluate and build the WSM package pack on the locked Guix"
        )["run"]
        self.assertIn("cp -- LICENSE archives/LICENSE", build)
        self.assertIn("sha256sum", build)
        self.assertIn("PROVENANCE.txt", build)
        self.assertIn("No OSI or GNU FSDG classification is claimed.", build)
        self.assertIn("actions/attest@v4", self.text)
        artifact = next(
            step for step in self.workflow["jobs"]["archive"]["steps"]
            if step.get("name") == "Keep the package as a workflow artifact"
        )
        self.assertIn("archives/LICENSE", artifact["with"]["path"])

    def test_publication_is_limited_to_an_explicit_existing_draft(self) -> None:
        self.assertIn("Attach the pack to an explicitly named existing Draft Release", self.text)
        self.assertIn("inputs.attach_to_draft != ''", self.text)
        self.assertIn("--json isDraft", self.text)
        self.assertIn("refusing: $TAG is not a draft release", self.text)
        self.assertNotIn("gh release list", self.text)
        self.assertNotIn("gh release create", self.text)

    def test_failure_is_visible_without_claiming_publication(self) -> None:
        self.assertIn("Report package build or publication failure", self.text)
        self.assertIn("No successful package publication is claimed.", self.text)


class H170SubstituteLaneTests(unittest.TestCase):
    def test_the_fixed_h170_substitute_lane_remains_separate(self) -> None:
        substitutes = (ROOT / ".github" / "workflows" / "substitutes.yml").read_text(encoding="utf-8")
        self.assertIn("drivers/profiles/h170-free-packages.scm", substitutes)
        self.assertIn("guix publish", substitutes)


if __name__ == "__main__":
    unittest.main()
