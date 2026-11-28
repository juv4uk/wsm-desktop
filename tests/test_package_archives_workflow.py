# SPDX-License-Identifier: LicenseRef-Volnist
"""The WSM-owned package lane builds only the manual, keyless wsm-tools pack."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"


class PackageArchivesWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.events = self.data[True]
        self.job = self.data["jobs"]["archive"]
        self.steps = self.job["steps"]

    def step(self, needle: str) -> dict:
        for step in self.steps:
            if needle in (step.get("name") or ""):
                return step
        raise AssertionError(f"no workflow step matching {needle!r}")

    def test_manual_main_only_with_scoped_write_permission(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.data["permissions"], {"contents": "write"})
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_only_the_wsm_owned_package_is_built_from_the_locked_source(self) -> None:
        build = self.step("Evaluate and build the WSM package pack")["run"]
        self.assertIn("guix time-machine -C channels.lock.scm", build)
        self.assertIn("--expression=", build)
        self.assertIn("(wsm packages wsm)", build)
        self.assertIn("wsm-tools", build)
        self.assertIn("--format=tarball", build)
        self.assertIn("--no-grafts", build)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)

    def test_pack_artifact_has_checksums_and_provenance(self) -> None:
        artifact = self.step("Keep the package as a workflow artifact")
        self.assertIn("actions/upload-artifact@v7", artifact["uses"])
        self.assertEqual(artifact["with"]["retention-days"], "30")
        build = self.step("Evaluate and build the WSM package pack")["run"]
        self.assertIn("SHA256SUMS", build)
        self.assertIn("PROVENANCE.txt", build)
        self.assertIn("guix-channels.txt", build)

    def test_optional_release_attachment_requires_an_existing_draft(self) -> None:
        attach = self.step("Attach the pack to an existing draft release")
        self.assertIn("inputs.attach_to_draft != ''", attach["if"])
        self.assertIn("--json isDraft", attach["run"])
        self.assertIn('!= "true"', attach["run"])
        self.assertNotIn("gh release create", self.text)

    def test_no_tag_trigger_or_private_signing_key(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        for marker in ("push:", "packages-*", "signing-key", "guix archive --generate-key", "secrets."):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_failure_report_does_not_claim_a_publication(self) -> None:
        step = self.step("Повідомити причину збою")
        self.assertIn("failure()", str(step.get("if")))
        self.assertIn("No binary package is claimed as published", step["run"])


if __name__ == "__main__":
    unittest.main()
