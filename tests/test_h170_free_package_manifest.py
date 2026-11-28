# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free package set is pinned, bounded and firmware-free."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drivers" / "profiles" / "h170-free-packages.scm"

EXPECTED = (
    "linux-libre",
    "mesa",
    "vulkan-loader",
    "vulkan-tools",
    "pciutils",
    "usbutils",
    "alsa-utils",
    "ethtool",
    "nvme-cli",
    "smartmontools",
    "lm-sensors",
    # WSM's own readers, Free Pascal builds. Added 2026-11-28, when the owner
    # ratified the implementation language: native binaries carry no
    # interpreter, which was the objection to the Python payload.
    "wsm-hwcheck-fpc",
    "wsm-classify-fpc",
    "wsm-partition-fpc",
    "wsm-profile-fpc",
    "wsm-preflight-fpc",
    "wsm-install-fpc",
)


class H170FreePackageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MANIFEST.read_text(encoding="utf-8")

    def test_manifest_contains_the_fixed_upstream_package_set(self) -> None:
        match = re.search(
            r"specifications->manifest\s*'\((.*?)\)\s*\)",
            self.text,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "manifest must return specifications->manifest")
        packages = tuple(re.findall(r'"([a-z0-9.+-]+)"', match.group(1)))
        self.assertEqual(packages, EXPECTED)
        self.assertEqual(len(packages), len(set(packages)))

    def test_no_wsm_owned_or_nonfree_payload_enters_the_free_set(self) -> None:
        for forbidden in (
            "wsm-tools",
            "linux-firmware",
            "nvidia-firmware",
            "nonguix",
            "nvda-580",
            "intel-microcode",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(f'"{forbidden}"', self.text)

    def test_known_gp107_kernel_limit_is_explicit(self) -> None:
        self.assertIn("7.3.5", self.text)
        self.assertIn("ed7fb901fce31588bd12ab95adc36ebcb51bc8ea", self.text)
        self.assertIn("does not prove H170/GP107", self.text)

    def test_manifest_is_not_a_supported_hardware_verdict(self) -> None:
        self.assertIn("not a supported-hardware verdict", self.text)
        self.assertIn("build/evidence manifest", self.text)


if __name__ == "__main__":
    unittest.main()
