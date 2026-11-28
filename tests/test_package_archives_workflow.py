# SPDX-License-Identifier: LicenseRef-Volnist
"""The legacy archive lane is a read-only fixed H170 Free package-plan check."""

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
        self.job = self.data["jobs"]["plan"]
        self.steps = self.job["steps"]

    def test_manual_main_only_and_read_only_permissions(self) -> None:
        self.assertEqual(set(self.events), {"workflow_dispatch"})
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_only_the_fixed_h170_manifest_is_evaluated(self) -> None:
        plan = next(step for step in self.steps if step.get("name") == "Evaluate the fixed H170 Free package plan")
        self.assertIn("guix time-machine -C channels.lock.scm", plan["run"])
        self.assertIn("--dry-run --no-grafts", plan["run"])
        self.assertIn("--manifest=drivers/profiles/h170-free-packages.scm", plan["run"])
        self.assertNotIn("wsm-tools", plan["run"])

    def test_no_package_input_or_binary_publication_path_exists(self) -> None:
        forbidden = (
            "inputs:",
            "github.event.inputs",
            "packages-*",
            "actions/upload-artifact",
            "gh release",
            "guix archive --export",
            "guix publish",
            "contents: write",
            "pages: write",
            "GH_TOKEN",
            "${{ inputs.",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_failure_report_is_read_only(self) -> None:
        step = next(step for step in self.steps if step.get("name") == "Summarize package-plan failure")
        self.assertIn("failure()", str(step.get("if")))
        self.assertIn("$GITHUB_STEP_SUMMARY", step["run"])


if __name__ == "__main__":
    unittest.main()
