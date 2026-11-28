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
    """The owner approved a bounded, provenance-bearing upstream H170 package release."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.job = self.workflow["jobs"]["archive"]

    def test_the_job_is_not_disabled(self) -> None:
        self.assertNotEqual(self.job.get("if"), "${{ false }}")
        self.assertNotIn("if: ${{ false }}", self.text)

    def test_the_owner_permission_is_recorded(self) -> None:
        self.assertIn("H170 Free", self.text)
        self.assertIn("upstream", self.text)

    def test_main_publisher_merge_tag_or_manual_dispatch_can_start_publication(self) -> None:
        events = self.workflow["on"]
        self.assertEqual(set(events), {"push", "workflow_dispatch"})
        self.assertEqual(events["push"]["branches"], ["main"])
        self.assertEqual(events["push"]["tags"], ["packages-h170-free-*"])
        self.assertEqual(
            events["push"]["paths"],
            [
                ".github/workflows/package-archives.yml",
                "channels.lock.scm",
                "drivers/profiles/h170-free-packages.scm",
            ],
        )
        gate = str(self.job.get("if", ""))
        self.assertIn("refs/heads/main", gate)
        self.assertIn("refs/tags/packages-h170-free-", gate)
        self.assertIn('EVENT_NAME" = "push"', self.text)
        self.assertIn('REF" = "refs/heads/main"', self.text)
        self.assertIn("git merge-base --is-ancestor", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_the_package_roots_come_from_the_fixed_h170_manifest(self) -> None:
        manifest_path = ROOT / "drivers" / "profiles" / "h170-free-packages.scm"
        manifest = manifest_path.read_text(encoding="utf-8")
        match = re.search(
            r"specifications->manifest\s*'\((.*?)\)\)", manifest, re.DOTALL
        )
        self.assertIsNotNone(match, "H170 Free manifest form was not found")
        packages = re.findall(r'"([a-z0-9.+-]+)"', match.group(1))
        expected = [
            "linux-libre",
            "mesa",
            "vulkan-loader",
            "vulkan-tools",
            "pciutils",
            "usbutils",
            "alsa-utils",
            "ethtool",
            "nvme-cli",
            "smartmontools",
            "lm-sensors",
        ]
        self.assertEqual(packages, expected)
        self.assertIn("drivers/profiles/h170-free-packages.scm", self.text)
        self.assertIn("expected = (", self.text)
        self.assertIn('test "${#PACKAGES[@]}" -eq 11', self.text)
        self.assertIn('test "${#STORE_PATHS[@]}" -eq 11', self.text)
        self.assertIn('mapfile -t PACKAGES < "$OUT/packages.txt"', self.text)
        for package in expected:
            with self.subTest(package=package):
                self.assertIn(f'"{package}"', self.text)
        for forbidden in (
            "wsm-tools",
            "wsm-live-tools",
            "linux-firmware",
            "nonguix",
            "nvda-580",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, packages)

    def test_no_untrusted_package_input_reaches_the_shell(self) -> None:
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("-L .", self.text)
        self.assertNotIn("for package in ${{", self.text)

    def test_the_archive_contains_the_recursive_store_closure(self) -> None:
        self.assertIn("archive --export --recursive", self.text)
        self.assertIn("h170-free-closure.nar", self.text)
        self.assertIn("store-paths.tsv", self.text)

    def test_provenance_records_derivations_and_effective_license_metadata(self) -> None:
        self.assertIn("build --derivations", self.text)
        self.assertIn("derivation_path", self.text)
        self.assertIn('show "$package"', self.text)
        self.assertIn("license:", self.text)
        self.assertIn("*.package-info.rec", self.text)
        self.assertIn("Pinned Guix package metadata", self.text)

    def test_archive_import_trust_and_checksums_are_distributed(self) -> None:
        self.assertIn("guix archive --generate-key", self.text)
        self.assertLess(
            self.text.index("guix archive --generate-key"),
            self.text.index("systemctl enable --now guix-daemon.service"),
        )
        self.assertIn("signing-key.pub", self.text)
        self.assertIn("guix archive --authorize", self.text)
        self.assertIn("guix archive --import", self.text)
        self.assertIn("SHA256SUMS", self.text)
        self.assertNotIn("secrets.GUIX_SIGNING_KEY", self.text)

    def test_the_build_has_github_provenance_attestation(self) -> None:
        self.assertIn("uses: actions/attest@v4", self.text)
        self.assertEqual(self.workflow["permissions"]["id-token"], "write")
        self.assertEqual(self.workflow["permissions"]["attestations"], "write")
        self.assertEqual(self.workflow["permissions"]["artifact-metadata"], "write")

    def test_publication_is_versioned_and_read_back_verified(self) -> None:
        self.assertIn("gh release create", self.text)
        self.assertIn("--prerelease", self.text)
        self.assertIn("gh release download", self.text)
        self.assertIn("sha256sum -c SHA256SUMS", self.text)
        self.assertIn("zstd -dc > /dev/null", self.text)

    def test_failures_leave_diagnostics_without_disabling_the_job(self) -> None:
        steps = self.job["steps"]
        reporters = [
            step for step in steps
            if "failure()" in str(step.get("if", ""))
            and "gh api" in str(step.get("run", ""))
        ]
        self.assertEqual(len(reporters), 1)




if __name__ == "__main__":
    unittest.main()
