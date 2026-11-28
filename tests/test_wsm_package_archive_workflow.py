# SPDX-License-Identifier: LicenseRef-Volnist
"""The WSM-owned package archive is a manual, attested and license-preserving Guix pack."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"


class WsmPackageArchiveWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.load(self.text, Loader=yaml.BaseLoader)
        self.events = self.data["on"]
        self.job = self.data["jobs"]["archive"]
        self.steps = self.job["steps"]

    def step(self, name: str) -> dict:
        for item in self.steps:
            if name in (item.get("name") or ""):
                return item
        raise AssertionError(f"missing workflow step: {name}")

    def test_only_manual_dispatch_can_start_the_package_archive(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_only_the_owner_package_is_built_on_the_pinned_lock(self) -> None:
        build = self.step("Evaluate and build the WSM package pack on the locked Guix")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("(wsm packages wsm)", build)
        self.assertIn("wsm-tools", build)
        self.assertIn("--format=tarball -C gzip", build)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)

    def test_pack_contains_the_license_and_has_matching_provenance(self) -> None:
        build = self.step("Evaluate and build the WSM package pack on the locked Guix")["run"]
        self.assertIn("cp -- LICENSE archives/LICENSE", build)
        self.assertIn("archives/LICENSE", build)
        self.assertIn("PROVENANCE.txt", build)
        verify = self.step("Verify the pack contains the WSM commands and license")["run"]
        for command in ("wsm-hwcheck", "wsm-install", "wsm-install-live"):
            self.assertIn(f"/bin/{command}$", verify)
        self.assertIn("/share/doc/wsm-tools/LICENSE$", verify)

    def test_artifact_is_attested_and_kept_with_all_license_metadata(self) -> None:
        attest = self.step("Attest the exact package and provenance files")
        self.assertEqual(attest["uses"], "actions/attest@v4")
        artifact = self.step("Keep the package as a workflow artifact")
        self.assertEqual(artifact["uses"], "actions/upload-artifact@v7")
        self.assertEqual(artifact["with"]["retention-days"], "30")
        self.assertEqual(artifact["with"]["if-no-files-found"], "error")
        for path in ("archives/*.tar.gz", "archives/LICENSE", "archives/SHA256SUMS", "archives/guix-channels.txt", "archives/PROVENANCE.txt"):
            self.assertIn(path, artifact["with"]["path"])

    def test_only_an_explicit_existing_draft_release_can_receive_the_pack(self) -> None:
        attach = self.step("Attach the pack to an explicitly named existing Draft Release")
        self.assertIn("inputs.attach_to_draft != ''", attach["if"])
        self.assertIn("--json isDraft", attach["run"])
        self.assertIn('!= "true"', attach["run"])
        self.assertIn("gh release download", attach["run"])
        self.assertIn("sha256sum -c SHA256SUMS.expected", attach["run"])
        self.assertNotIn("gh release list", self.text)
        self.assertNotIn("gh release create", self.text)

    def test_no_private_signing_key_or_unrequested_trigger_exists(self) -> None:
        for marker in ("push:", "packages-*", "signing-key", "guix archive --generate-key", "secrets."):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_failure_report_does_not_claim_a_publication(self) -> None:
        step = self.step("Report package build or publication failure")
        self.assertIn("failure()", step["if"])
        self.assertIn("No successful package publication is claimed.", step["run"])


if __name__ == "__main__":
    unittest.main()
