# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks for the published WSM ISO release artifacts."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IsoReleaseTests(unittest.TestCase):
    def test_live_profiles_define_console_password_and_wheel(self) -> None:
        shadow = "$6$saltWSM$cnmIeJgvQ38p5Wy5YgmTnHnFhAtoHwikjDotqpSoIRHdmGjWQWyLKU4L67GZBKvv0YNgBMUqCWmHQC4gFMnoY0"
        for profile in ("systems/live-compat.scm", "systems/live-iso.scm"):
            text = (ROOT / profile).read_text(encoding="utf-8")
            self.assertIn(shadow, text, profile)
            self.assertIn('"wheel"', text, profile)
            self.assertIn("(allow-empty-passwords? #f)", text, profile)

    def test_reassembly_script_is_present_and_executable(self) -> None:
        script = ROOT / "scripts" / "reassemble-iso.sh"
        self.assertTrue(script.is_file())
        self.assertTrue(script.stat().st_mode & 0o111)
        text = script.read_text(encoding="utf-8")
        self.assertIn('sha256sum "$output"', text)

    def test_checksums_name_the_hardened_images(self) -> None:
        sums = (ROOT / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
        for name, digest in (
            ("wsm-desktop-kde-hardened-20261125.iso",
             "d1a000f8c465b496565b0f611ae6f65095086a8457c663f212ca5b17073fd7ef"),
            ("wsm-desktop-kde-hardened-20261126-login.iso",
             "deec276886656b99c3f3f58e51d9fd3fc89baf814e38e5f6e9ddc704976b17f7"),
        ):
            self.assertIn(name, sums)
            self.assertIn(digest, sums)

    def test_checksums_name_the_compatibility_images(self) -> None:
        sums = (ROOT / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
        for name, digest in (
            ("wsm-desktop-kde-compat-nvidia-20261126.iso",
             "19a1ca6fc1377fbfb878e1cf670fc521faf7ea0389579f3a6501d956b6df6da0"),
            ("wsm-desktop-kde-compat-nvidia-20261126-login.iso",
             "41486ff5c86db95c63a45c7fb1cf753e604eb97fef1f777093c4325a4edebd60"),
        ):
            self.assertIn(name, sums)
            self.assertIn(digest, sums)

    def test_release_notes_explain_the_split(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("2 GiB", notes)
        self.assertIn(".part001", notes)

    def test_compatibility_assets_are_recorded_without_overclaiming_provenance(self) -> None:
        notes = (ROOT / "ISO-RELEASE.md").read_text(encoding="utf-8")
        profile = (ROOT / "systems/live-compat.scm").read_text(encoding="utf-8")
        self.assertIn("шість базових\nчастин Compatibility/NVIDIA ISO", notes)
        self.assertIn("Публікація asset ≠ ліцензійне схвалення", notes)
        self.assertIn("redistribution NOT CLEARED", notes)
        self.assertIn("source_commit", notes)
        self.assertIn("немає `release-manifest.json`", notes)
        self.assertIn("909c33c038ab8504a4782f741ec13f6063335606f6db7051675d75436fc9f517", notes)
        self.assertIn("557e8f1f3baa6456bf6cd6fe5ef28df424a42e1df58f300b22bedb6349cbb33a", notes)
        self.assertIn("580.178.04", notes)
        self.assertIn("7.3.5", notes)
        self.assertIn("§1.1(d)", notes)
        self.assertIn("patchelf", notes)
        self.assertIn("їхній redistribution status лишається `NOT CLEARED`", notes)
        self.assertIn("NVIDIA binary redistribution: NOT CLEARED", profile)
        self.assertIn("580.196.11", notes)
        self.assertIn("7.3.6", notes)
        self.assertIn("локально зібрано в", profile)
        self.assertIn("QEMU TCG BIOS boot", profile)
        self.assertIn("API verified 2026-11-28", profile)
        self.assertIn("source_commit unknown", profile)
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
