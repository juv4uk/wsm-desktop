# SPDX-License-Identifier: LicenseRef-Volnist
"""The WSM-owned package archive is a manual, keyless Guix pack."""

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
        for step in self.steps:
            if name in (step.get("name") or ""):
                return step
        raise AssertionError(f"missing workflow step: {name}")

    def test_only_manual_dispatch_can_start_the_package_archive(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_only_the_owner_package_is_built(self) -> None:
        build = self.step("Evaluate and build the WSM package pack")["run"]
        self.assertIn("(wsm packages wsm)", build)
        self.assertIn("wsm-tools", build)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)

    def test_pack_is_self_contained_and_does_not_need_a_cache_key(self) -> None:
        build = self.step("Evaluate and build the WSM package pack")["run"]
        self.assertIn("--format=tarball -C gzip", build)
        self.assertIn('output="archives/wsm-tools-${GITHUB_SHA:0:12}.tar.gz"', build)
        self.assertIn("--no-grafts", build)
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertNotIn("guix archive --export", self.text)
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("guix archive --generate-key", self.text)

    def test_pack_provenance_and_checksum_are_kept(self) -> None:
        build = self.step("Evaluate and build the WSM package pack")["run"]
        self.assertIn("channels.lock.scm", build)
        self.assertIn("SHA256SUMS", build)
        self.assertIn("PROVENANCE.txt", build)
        self.assertIn("cp -- LICENSE archives/LICENSE", build)
        self.assertIn("LICENSE", self.text)
        artifact = self.step("Keep the package as a workflow artifact")
        self.assertIn("actions/upload-artifact@v7", artifact["uses"])
        self.assertEqual(artifact["with"]["retention-days"], "30")
        self.assertIn("archives/LICENSE", artifact["with"]["path"])

    def test_the_runtime_pack_contains_the_license_text(self) -> None:
        verify = self.step("Verify the pack contains the installed WSM commands")["run"]
        self.assertIn("/share/doc/wsm-tools/LICENSE$", verify)
        self.assertIn("actions/attest@v4", self.text)

    def test_only_an_existing_draft_release_can_receive_the_pack(self) -> None:
        step = self.step("Attach the pack to an existing draft release")
        self.assertIn("inputs.attach_to_draft != ''", step["if"])
        self.assertIn("isDraft", step["run"])
        self.assertIn('!= "true"', step["run"])
        self.assertNotIn("gh release create", self.text)
        self.assertIn("archives/LICENSE", step["run"])

    def test_failure_is_visible_without_claiming_a_publication(self) -> None:
        step = self.step("Повідомити причину збою")
        self.assertIn("failure()", step["if"])
        self.assertIn("GITHUB_STEP_SUMMARY", step["run"])
        self.assertIn("No binary package is claimed as published", step["run"])
        self.assertIn("commits/$GITHUB_SHA/comments", step["run"])


if __name__ == "__main__":
    unittest.main()
