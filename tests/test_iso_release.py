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

    def test_checksums_name_the_compatibility_image(self) -> None:
        sums = (ROOT / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
        self.assertIn("wsm-desktop-kde-compat-nvidia-20261126.iso", sums)
        self.assertIn("19a1ca6fc1377fbfb878e1cf670fc521faf7ea0389579f3a6501d956b6df6da0", sums)

    def test_release_notes_explain_the_split(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("2 GiB", notes)
        self.assertIn(".part001", notes)

    def test_compatibility_candidate_is_not_misrepresented_as_published(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        profile = (ROOT / "systems/live-compat.scm").read_text(encoding="utf-8")
        self.assertIn("шість бінарних частин ще не завантажено до GitHub Release", notes)
        self.assertIn("не повертає жодної з шести", notes)
        self.assertIn("580.178.04", notes)
        self.assertIn("7.3.5", notes)
        self.assertIn("580.196.11", notes)
        self.assertIn("7.3.6", notes)
        self.assertIn("локально зібрано в", profile)
        self.assertIn("QEMU TCG BIOS boot", profile)
        self.assertIn("ще не завантажено до GitHub Release", profile)
        self.assertIn("Physical H170 / GTX 1050 Ti binding", profile)
        self.assertNotIn("Compatibility package closure та image build: NOT RUN", profile)

    def test_release_documents_hardware_targeted_compatibility_build(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        for fact in ("localmodconfig", "69 модулів", "580.178.04",
                     "modprobe.blacklist=nouveau", "gp107", "accel=tcg",
                     "wsm-kde login:"):
            self.assertIn(fact, notes)


if __name__ == "__main__":
    unittest.main()
