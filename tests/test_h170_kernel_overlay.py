# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free kernel overlay must remain a one-patch upstream derivative."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEME = ROOT / "wsm" / "packages" / "linux-libre.scm"
PATCH = ROOT / "wsm" / "packages" / "patches" / "linux-libre-h170-nouveau-atomic.patch"
MATRIX = ROOT / "docs" / "hardware" / "H170-FIRMWARE-MATRIX.md"


class H170LinuxLibreOverlayTests(unittest.TestCase):
    def test_patch_is_the_upstream_gp107_atomic_modesetting_fix(self) -> None:
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn(
            "From ed7fb901fce31588bd12ab95adc36ebcb51bc8ea ",
            patch,
        )
        self.assertEqual(patch.count("diff --git "), 1)
        self.assertIn("nouveau_mode_config_funcs_atomic", patch)
        self.assertIn("drm_atomic_helper_commit", patch)
        self.assertIn("drm_atomic_helper_check", patch)
        self.assertIn("drm_drv_uses_atomic_modeset(dev)", patch)

    def test_package_inherits_upstream_recipe_and_appends_existing_patches(self) -> None:
        scheme = SCHEME.read_text(encoding="utf-8")
        self.assertIn("(inherit linux-libre)", scheme)
        self.assertIn("(inherit (package-source linux-libre))", scheme)
        self.assertIn("(origin-patches (package-source linux-libre))", scheme)
        self.assertIn("(append (origin-patches", scheme)
        self.assertIn("search-path %load-path", scheme)
        self.assertIn('(name "linux-libre-h170")', scheme)

    def test_overlay_does_not_add_proprietary_driver_or_firmware_packages(self) -> None:
        scheme = SCHEME.read_text(encoding="utf-8").lower()
        self.assertNotIn("nonguix", scheme)
        self.assertNotIn("nvidia-firmware", scheme)
        self.assertNotIn("firmware-nvidia", scheme)
        self.assertNotIn("nvidia-kernel", scheme)

    def test_documentation_keeps_runtime_and_compute_claims_unproven(self) -> None:
        text = MATRIX.read_text(encoding="utf-8").lower()
        self.assertIn("linux-libre-h170", text)
        self.assertIn("не доводить", text)
        self.assertIn("feсs", text.replace("фecs", "feсs"))


if __name__ == "__main__":
    unittest.main()
