# SPDX-License-Identifier: LicenseRef-Volnist
"""Keep package archives manual and block an unapproved public cache workflow."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / ".github" / "workflows" / "substitutes.yml"
ARCHIVE_WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"
SUBSTITUTE_DOC = ROOT / "docs" / "SUBSTITUTES.md"


class SubstituteWorkflowTests(unittest.TestCase):
    def test_no_automatic_public_substitute_publisher_is_installed(self) -> None:
        self.assertFalse(
            PUBLISHER.exists(),
            "public substitute publication needs owner-approved license, Phase B and key custody",
        )

    def test_package_archives_are_manual_only(self) -> None:
        text = ARCHIVE_WORKFLOW.read_text(encoding="utf-8")
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        events = workflow["on"]
        self.assertEqual(set(events), {"workflow_dispatch"})
        self.assertNotIn("push", events)
        self.assertNotIn("pull_request", events)
        self.assertIn("actions/upload-artifact@v7", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("guix publish", text)
        self.assertNotIn("gh release upload", text)

    def test_docs_describe_staging_not_a_live_cache(self) -> None:
        text = SUBSTITUTE_DOC.read_text(encoding="utf-8").lower()
        self.assertIn("публікація не запускалися", text)
        self.assertIn("ключ підпису", text)
        self.assertIn("не створений", text)
        self.assertIn("issue #367", text)
        self.assertIn("phase b", text)
        self.assertIn("нічого не публікує", text)


if __name__ == "__main__":
    unittest.main()
