# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks for the published WSM ISO release artifacts."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IsoReleaseTests(unittest.TestCase):
    def test_reassembly_script_is_present_and_executable(self) -> None:
        script = ROOT / "scripts" / "reassemble-iso.sh"
        self.assertTrue(script.is_file())
        self.assertTrue(script.stat().st_mode & 0o111)
        text = script.read_text(encoding="utf-8")
        self.assertIn('sha256sum "$output"', text)

    def test_checksums_name_the_hardened_image(self) -> None:
        sums = (ROOT / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
        self.assertIn("wsm-desktop-kde-hardened-20261125.iso", sums)
        self.assertIn("d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef", sums)

    def test_release_notes_explain_the_split(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("2 GiB", notes)
        self.assertIn(".part001", notes)


if __name__ == "__main__":
    unittest.main()
