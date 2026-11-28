# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free cache is fixed, upstream-only, and distinct from the custom kernel."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drivers" / "profiles" / "h170-free-packages.scm"
KERNEL_PACKAGE = ROOT / "wsm" / "packages" / "linux-libre.scm"

EXPECTED = (
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
)


class H170FreePackageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MANIFEST.read_text(encoding="utf-8")

    def test_manifest_contains_exactly_the_fixed_ten_upstream_roots(self) -> None:
        match = re.search(
            r"specifications->manifest\s*'\((.*?)\)\s*\)",
            self.text,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "manifest must return specifications->manifest")
        packages = tuple(re.findall(r'"([a-z0-9.+-]+)"', match.group(1)))
        self.assertEqual(packages, EXPECTED)
        self.assertEqual(len(packages), len(set(packages)))

    def test_no_wsm_owned_or_nonfree_package_is_in_the_upstream_roots(self) -> None:
        match = re.search(
            r"specifications->manifest\s*'\((.*?)\)\s*\)",
            self.text,
            re.DOTALL,
        )
        assert match is not None
        packages = set(re.findall(r'"([a-z0-9.+-]+)"', match.group(1)))
        for forbidden in (
            "wsm-tools",
            "wsm-live-tools",
            "linux-firmware",
            "nvidia-firmware",
            "nonguix",
            "nvda-580",
            "intel-microcode",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, packages)

    def test_custom_h170_kernel_is_separate_from_the_upstream_cache_roots(self) -> None:
        self.assertIn("linux-libre-h170", self.text)
        kernel = KERNEL_PACKAGE.read_text(encoding="utf-8")
        self.assertIn("(inherit linux-libre)", kernel)
        self.assertIn("linux-libre-h170-nouveau-atomic.patch", kernel)

    def test_manifest_is_not_a_hardware_support_verdict(self) -> None:
        self.assertIn("not a supported-hardware verdict", self.text.lower())
        self.assertIn("build/evidence manifest", self.text.lower())


if __name__ == "__main__":
    unittest.main()
