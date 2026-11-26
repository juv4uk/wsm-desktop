# SPDX-License-Identifier: LicenseRef-Volnist
"""README must not be a release behind its own metadata.

The repository shipped this defect once: README said «доступний лише Hardware
Preview RC1» while `RELEASE-INFO.json` described rc4 and the releases page
carried rc2 and rc3. Both statements were in the same file — line 43 linked the
RC3 minimal live release, line 182 called RC1 the only one.

A reader who trusts the summary gets a wrong picture of the project. So the
summary line must name the version the metadata describes, and it must not
silently present an older one as the current state.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RELEASE_INFO = ROOT / "RELEASE-INFO.json"

STAGE_LINE = "**Стадія проєкту:**"


def stage_paragraph(text: str) -> str:
    start = text.index(STAGE_LINE)
    end = text.index("\n\n", start)
    return text[start:end]


class ReadmeStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = README.read_text(encoding="utf-8")
        self.version = json.loads(RELEASE_INFO.read_text(encoding="utf-8"))["version"]

    def test_stage_names_the_metadata_version(self) -> None:
        self.assertIn(self.version, stage_paragraph(self.text))

    def test_stage_does_not_call_an_older_release_current(self) -> None:
        """If README links a newer RC, the summary may not stop at an older one."""
        mentioned = {int(match) for match in re.findall(r"0\.1\.0-rc(\d+)", self.text)}
        self.assertTrue(mentioned, "README should mention at least one release")
        paragraph = stage_paragraph(self.text)
        newest = max(mentioned)
        self.assertIn(
            f"rc{newest}",
            paragraph,
            f"the summary stops before rc{newest}, which the same README mentions",
        )

    def test_unpublished_version_is_labelled(self) -> None:
        """Metadata may describe a release that does not exist yet; say so."""
        paragraph = stage_paragraph(self.text)
        if self.version in paragraph and "не опубліковано" in paragraph:
            return
        self.assertIn(
            "не опубліковано",
            paragraph,
            "if the metadata version is not released, the summary must say so",
        )


if __name__ == "__main__":
    unittest.main()
