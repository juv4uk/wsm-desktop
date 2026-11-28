# SPDX-License-Identifier: LicenseRef-Volnist
"""The substitute workflow must fail closed until owner gates are evidenced."""

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
        self.job = self.data["jobs"]["publish"]
        self.steps = self.job["steps"]

    def test_the_workflow_parses_and_is_manual_only(self) -> None:
        self.assertEqual(set(self.data["on"]), {"workflow_dispatch"})
        self.assertNotIn("push", self.data["on"])
        self.assertNotIn("schedule", self.data["on"])

    def test_it_is_an_explicit_fail_closed_gate(self) -> None:
        self.assertIn("PUBLICATION_PAUSED", self.text)
        self.assertIn("exit 1", "\n".join(str(x.get("run", "")) for x in self.steps))
        self.assertIn("#367", self.text)
        self.assertIn("#534", self.text)
        self.assertIn("Phase B", self.text)

    def test_workflow_and_job_permissions_are_read_only(self) -> None:
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.job["permissions"], {"contents": "read"})
        for forbidden in ("pages", "id-token", "deployments", "actions: write"):
            self.assertNotIn(forbidden, self.text)

    def test_there_are_no_package_inputs_or_shell_interpolation(self) -> None:
        self.assertNotIn("inputs:", self.text)
        self.assertNotIn("github.event.inputs", self.text)
        self.assertNotIn("PACKAGES=", self.text)
        self.assertNotIn("wsm-tools", self.text)

    def test_it_does_not_read_or_install_signing_key_material(self) -> None:
        self.assertNotIn("GUIX_SIGNING_KEY", self.text)
        self.assertNotIn("signing-key.sec", self.text)
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("gh secret set", self.text)

    def test_it_does_not_build_export_sign_or_publish(self) -> None:
        for forbidden in (
            "guix build",
            "guix publish",
            "guix archive",
            "gh release create",
            "gh release upload",
            "upload-pages-artifact",
            "deploy-pages",
            "narinfo_to_release_urls.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_no_secret_or_write_capability_is_granted(self) -> None:
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("pages: write", self.text)


if __name__ == "__main__":
    unittest.main()
