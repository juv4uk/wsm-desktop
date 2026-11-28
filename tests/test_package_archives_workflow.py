# SPDX-License-Identifier: LicenseRef-Volnist
"""ADR 0010 WSM-owned guix pack publication policy."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"


class PackageArchivesWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.events = self.data["on"]
        self.job = self.data["jobs"]["archive"]
        self.steps = self.job["steps"]

    def named(self, name: str) -> dict:
        for step in self.steps:
            if step.get("name") == name:
                return step
        raise AssertionError(f"missing step: {name}")

    def test_manual_main_only_and_draft_only(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.data["permissions"]["contents"], "write")
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/main'")
        self.assertIn("--draft", self.text)
        self.assertIn("isDraft", self.text)
        self.assertNotIn("--draft=false", self.text)
        self.assertNotIn("gh release edit", self.text)
        self.assertNotIn("push:", self.text)
        self.assertNotIn("schedule:", self.text)

    def test_only_the_fixed_wsm_package_is_built(self) -> None:
        build = self.named("Build the fixed WSM package pack")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("--expression='(begin (use-modules (wsm packages wsm)) wsm-tools)'", build)
        self.assertIn("wsm-tools", build)
        self.assertIn("-f tarball", build)
        self.assertIn("-C zstd", build)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        for forbidden in ("linux-libre", "mesa", "nonguix", "nvda-580", "linux-firmware"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, build)

    def test_package_module_and_effective_license_are_evaluated(self) -> None:
        evaluate = self.named("Evaluate the package module and exact LicenseRef metadata")["run"]
        self.assertIn("tests/guix/source-module-evaluation.scm", evaluate)
        self.assertIn("guix time-machine -C channels.lock.scm -- repl", evaluate)

    def test_pack_is_self_contained_and_expected_commands_are_checked(self) -> None:
        build = self.named("Build the fixed WSM package pack")["run"]
        for command in ("wsm-hwcheck", "wsm-install", "wsm-install-live"):
            with self.subTest(command=command):
                self.assertIn(command, build)
        self.assertIn("propagated runtime inputs", self.text)

    def test_github_attestation_is_created_for_the_pack(self) -> None:
        attest = self.named("Attest the exact pack and provenance")
        self.assertEqual(attest["uses"], "actions/attest@v4")
        self.assertIn("archives/wsm-tools-pack.tar.zst", attest["with"]["subject-path"])
        self.assertEqual(self.data["permissions"]["id-token"], "write")
        self.assertEqual(self.data["permissions"]["attestations"], "write")

    def test_release_assets_are_unique_and_remain_draft_after_readback(self) -> None:
        release = self.named("Create a dedicated Draft Release and verify read-back")["run"]
        self.assertIn("GITHUB_RUN_ID", release)
        self.assertIn("GITHUB_RUN_ATTEMPT", release)
        self.assertIn("gh release create", release)
        self.assertIn("gh release download", release)
        self.assertIn("sha256sum -c SHA256SUMS", release)
        self.assertIn("zstd -t", release)
        self.assertIn("isDraft", release)
        self.assertNotIn("gh release list", self.text)
        self.assertNotIn("latest draft", self.text.lower())

    def test_license_metadata_is_not_misrepresented_as_gpl(self) -> None:
        package = (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8")
        self.assertIn('"ВОЛЬНІСТЬ"', package)
        self.assertIn('"file://LICENSE"', package)
        self.assertNotIn("(license gpl3+)", package)

    def test_no_signing_key_or_substitute_server_is_added(self) -> None:
        for forbidden in ("guix archive --generate-key", "GUIX_SIGNING_KEY", "signing-key.sec", "guix publish"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_failure_report_does_not_claim_success(self) -> None:
        failure = self.named("Report the exact failure without claiming publication")
        self.assertEqual(failure["if"], "failure()")
        self.assertIn("No successful package build or Release is claimed", failure["run"])


if __name__ == "__main__":
    unittest.main()
