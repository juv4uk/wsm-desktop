# SPDX-License-Identifier: LicenseRef-Volnist
"""Guix archive export is disabled until signer custody and the fixed allowlist."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"
DOC = ROOT / "docs" / "SUBSTITUTES.md"


class PackageArchiveWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.job = self.data["jobs"]["archive"]

    def test_workflow_is_manual_only(self) -> None:
        self.assertIn("workflow_dispatch", self.data[True])
        self.assertNotIn("push", self.data[True])
        self.assertNotIn("pull_request", self.data[True])

    def test_archive_job_is_disabled(self) -> None:
        self.assertEqual(self.job.get("if"), "${{ false }}")
        self.assertIn("NOT_AUTHORIZED", self.text)

    def test_arbitrary_package_input_is_removed(self) -> None:
        self.assertNotIn("inputs.packages", self.text)
        self.assertNotIn("github.event.inputs.packages", self.text)
        self.assertNotIn("packages:", self.text)

    def test_no_nar_export_artifact_or_release_upload_runs(self) -> None:
        for marker in (
            "guix archive --export", "upload-artifact",
            "gh release upload", "GUIX_SIGNING_KEY",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_permissions_are_read_only(self) -> None:
        self.assertEqual(self.data["permissions"], {"contents": "read"})

    def test_hardware_build_evidence_is_the_non_exporting_path(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "hw-build-evidence.yml").read_text(encoding="utf-8")
        self.assertIn("drivers/profiles/h170-free-packages.scm", workflow)
        self.assertIn("nar_sha256", workflow)
        self.assertNotIn("guix archive --export", workflow)
        self.assertNotIn("upload-artifact", workflow)

    def test_document_explains_archive_signatures_and_key_custody(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("підписує", text.lower())
        self.assertIn("signing-key.sec", text)
        self.assertIn("NOT_PUBLISHED", text)


if __name__ == "__main__":
    unittest.main()
