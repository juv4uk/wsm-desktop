# SPDX-License-Identifier: LicenseRef-Volnist
"""Substitute publication stays disabled pending explicit key custody."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "substitutes.yml"
DOC = ROOT / "docs" / "SUBSTITUTES.md"


class SubstituteWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.job = self.data["jobs"]["publish"]

    def test_workflow_is_manual_only_and_parses(self) -> None:
        self.assertIn("workflow_dispatch", self.data[True])
        self.assertNotIn("push", self.data[True])
        self.assertNotIn("pull_request", self.data[True])

    def test_publisher_job_is_fail_closed(self) -> None:
        self.assertEqual(self.job.get("if"), "${{ false }}")
        self.assertIn("NOT_AUTHORIZED", self.text)

    def test_no_user_controlled_package_input_or_shell_interpolation(self) -> None:
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)
        self.assertNotIn("packages:", self.text)

    def test_no_signing_key_or_publish_actions_are_configured(self) -> None:
        for marker in (
            "GUIX_SIGNING_KEY", "guix publish", "signing-key.sec",
            "upload-pages-artifact", "deploy-pages", "gh release upload",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_workflow_has_read_only_permissions(self) -> None:
        self.assertEqual(self.data["permissions"], {"contents": "read"})

    def test_document_matches_the_fail_closed_state(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("NOT_AUTHORIZED", text)
        self.assertIn("NOT_PUBLISHED", text)
        self.assertIn("Phase B", text)
        self.assertIn("#367", text)


if __name__ == "__main__":
    unittest.main()
