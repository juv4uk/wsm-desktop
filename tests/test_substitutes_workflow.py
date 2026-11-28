# SPDX-License-Identifier: LicenseRef-Volnist
"""Substitute publication must stay disabled until explicit owner decisions."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "substitutes.yml"


class SubstituteWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_workflow_is_manual_only(self) -> None:
        events = self.data["on"]
        self.assertEqual(set(events), {"workflow_dispatch"})

    def test_publication_job_is_explicitly_disabled(self) -> None:
        job = self.data["jobs"]["publish"]
        self.assertEqual(job["if"], "${{ false }}")
        self.assertIn("вимкнено", self.text.lower())

    def test_no_publication_permissions_are_granted(self) -> None:
        permissions = self.data["permissions"]
        self.assertEqual(permissions, {"contents": "read"})

    def test_no_signing_key_or_deployment_action_is_referenced(self) -> None:
        for marker in (
            "secrets.",
            "GUIX_SIGNING_KEY",
            "signing-key.sec",
            "guix archive --generate-key",
            "gh release upload",
            "actions/deploy-pages",
            "actions/upload-pages-artifact",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_it_names_the_required_owner_gates(self) -> None:
        self.assertIn("#367", self.text)
        self.assertIn("endpoint", self.text.lower())
        self.assertIn("key custody", self.text.lower())


if __name__ == "__main__":
    unittest.main()
