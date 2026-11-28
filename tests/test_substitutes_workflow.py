# SPDX-License-Identifier: LicenseRef-Volnist
"""ADR 0010 keeps the long-lived substitute service explicitly disabled."""

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

    def test_workflow_is_manual_only_and_does_not_start_a_job(self) -> None:
        self.assertEqual(set(self.data["on"]), {"workflow_dispatch"})
        self.assertNotIn("push:", self.text)
        self.assertNotIn("schedule:", self.text)
        self.assertEqual(self.data["jobs"]["publish"]["if"], "false")

    def test_disabled_workflow_does_not_request_publish_permissions(self) -> None:
        permissions = self.data.get("permissions", {})
        self.assertEqual(permissions.get("contents"), "read")
        self.assertNotIn("pages", permissions)
        self.assertNotIn("id-token", permissions)

    def test_no_signing_key_is_created_or_requested(self) -> None:
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("GUIX_SIGNING_PUBLIC_KEY", self.text)
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("guix archive --generate-key", self.text)
        self.assertNotIn("signing-key.sec", self.text)

    def test_no_build_or_substitute_endpoint_is_started(self) -> None:
        for forbidden in (
            "guix build",
            "guix publish",
            "gh release create",
            "actions/deploy-pages",
            "narinfo",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_disabled_reason_points_to_the_canonical_decision(self) -> None:
        self.assertIn("ADR 0010", self.text)
        self.assertIn("wsm-tools", self.text)


if __name__ == "__main__":
    unittest.main()
