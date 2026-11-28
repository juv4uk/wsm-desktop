# SPDX-License-Identifier: LicenseRef-Volnist
"""The first distribution lane follows ADR 0010: WSM-owned guix pack draft."""

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
        self.build = next(step for step in self.steps if step.get("id") == "build-pack")
        self.release = next(
            step for step in self.steps
            if step.get("name") == "Create a draft release and verify read-back"
        )

    def test_manual_main_only_with_write_scope_for_draft_release(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.data["permissions"], {"contents": "write"})
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/main'")
        self.assertNotIn("push:", self.text)

    def test_only_the_owner_package_is_evaluated_and_packed(self) -> None:
        command = self.build["run"]
        self.assertIn("wsm-tools", command)
        self.assertIn("(wsm packages wsm)", command)
        self.assertIn("--format=tarball", command)
        self.assertIn("guix time-machine -C channels.lock.scm", command)
        for forbidden in ("linux-libre", "mesa", "nonguix", "nvda-580", "linux-firmware"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, command)

    def test_package_list_is_fixed_and_not_supplied_by_dispatch_input(self) -> None:
        self.assertNotIn("inputs:", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("PACKAGES=", self.text)

    def test_pack_has_runtime_closure_and_no_substitute_signing_key(self) -> None:
        command = self.build["run"]
        self.assertIn("--no-grafts", command)
        self.assertIn("--symlink=/opt/wsm/bin=bin", command)
        self.assertNotIn("guix archive", self.text)
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("guix publish", self.text)

    def test_pack_and_package_inputs_are_verified(self) -> None:
        command = self.build["run"]
        for expected in ("wsm-hwcheck", "wsm-install", "wsm-install-live"):
            with self.subTest(expected=expected):
                self.assertIn(expected, command)
        self.assertIn("CHANNEL-INPUTS.sha256", self.text)
        self.assertIn("PROVENANCE.txt", self.text)
        self.assertIn("LICENSE", self.text)
        self.assertIn("SHA256SUMS", self.text)

    def test_only_a_draft_release_is_created_and_read_back(self) -> None:
        command = self.release["run"]
        self.assertIn("gh release create", command)
        self.assertIn("--draft", command)
        self.assertIn("isDraft", command)
        self.assertIn("gh release download", command)
        self.assertIn("sha256sum -c SHA256SUMS", command)
        self.assertNotIn("gh release edit", self.text)
        self.assertNotIn("--prerelease", self.text)

    def test_failure_is_reported_and_does_not_claim_success(self) -> None:
        reports = [
            step for step in self.steps
            if step.get("if") == "failure()"
            and "commits/$GITHUB_SHA/comments" in step.get("run", "")
        ]
        self.assertEqual(len(reports), 1)
        self.assertIn("No successful package build or release is claimed", reports[0]["run"])


if __name__ == "__main__":
    unittest.main()
