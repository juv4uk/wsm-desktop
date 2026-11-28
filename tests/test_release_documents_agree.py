# SPDX-License-Identifier: LicenseRef-Volnist
"""The release documents must describe the same release.

Before RC6 the repository held four answers at once: `RELEASE-REQUEST.txt` asked
for `0.1.0-rc6-minimal-live`, `RELEASE-INFO.json` and `RELEASE-NOTES.md` said
`0.1.0-rc4`, and `docs/RELEASE-TESTING.md` gave commands for a tarball named
after RC1. Someone following the testing guide would run `tar -xzf
wsm-desktop-0.1.0-rc1-source.tar.gz` against a release that does not contain that
file.

The notes may legitimately lag the requested build — a candidate is built before
its notes are written. What may not happen is a document that names a *file* of a
version other than the one being requested.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "RELEASE-REQUEST.txt"
INFO = ROOT / "RELEASE-INFO.json"
NOTES = ROOT / "RELEASE-NOTES.md"
TESTING = ROOT / "docs" / "RELEASE-TESTING.md"

TAG = re.compile(r"^0\.1\.0-rc[0-9]+", re.MULTILINE)
ARTIFACT = re.compile(r"wsm-desktop-0\.1\.0-rc[0-9]+")


def requested_version() -> str:
    tags = [
        line.strip()
        for line in REQUEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(tags) == 1, f"RELEASE-REQUEST.txt must hold exactly one tag, got {tags}"
    return tags[0].replace("-minimal-live", "")


class ReleaseDocumentsAgreeTests(unittest.TestCase):
    def test_request_names_exactly_one_version(self) -> None:
        self.assertRegex(requested_version(), r"^0\.1\.0-rc[0-9]+$")

    def test_notes_version_matches_release_info(self) -> None:
        version = json.loads(INFO.read_text(encoding="utf-8"))["version"]
        self.assertIn(version, NOTES.read_text(encoding="utf-8"))

    def test_testing_guide_does_not_pin_a_versioned_artifact_name(self) -> None:
        """A filename in an instruction must come from the release, not memory."""
        text = TESTING.read_text(encoding="utf-8")
        pinned = sorted(set(ARTIFACT.findall(text)))
        self.assertEqual(
            pinned,
            [],
            "docs/RELEASE-TESTING.md pins artifact names of a specific version: "
            + ", ".join(pinned)
            + " — take the name from the release page instead",
        )

    def test_testing_guide_points_at_the_release_page(self) -> None:
        self.assertIn("сторінки релізу", TESTING.read_text(encoding="utf-8"))

    def test_the_gap_between_request_and_notes_is_visible(self) -> None:
        """A candidate ahead of its notes is fine only if the notes say so."""
        requested = requested_version()
        notes = NOTES.read_text(encoding="utf-8")
        if requested in notes:
            return
        self.assertIn(
            "кандидат",
            notes.lower(),
            "RELEASE-NOTES describes an older release than the one requested; "
            "either update it or say plainly that a candidate is being prepared",
        )


if __name__ == "__main__":
    unittest.main()
