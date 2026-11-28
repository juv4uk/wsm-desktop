# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free package manifest and publication workflow stay upstream-only."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drivers" / "profiles" / "h170-free-packages.scm"
WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

EXPECTED = {
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
}


class H170FreePackageManifestTests(unittest.TestCase):
    def test_manifest_contains_the_fixed_h170_upstream_roots(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        actual = {
            line.strip().strip('"')
            for line in text.splitlines()
            if line.strip().startswith('"') and line.strip().endswith('"')
        }
        self.assertEqual(actual, EXPECTED)

    def test_manifest_excludes_wsm_owned_and_nonfree_roots(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8").lower()
        for forbidden in (
            "wsm-tools",
            "wsm-live-tools",
            "nonguix",
            "nvidia-firmware",
            "linux-firmware",
            "intel-microcode",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_archive_workflow_uses_the_fixed_manifest_and_exact_lock(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("channels.lock.scm", text)
        self.assertIn("drivers/profiles/h170-free-packages.scm", text)
        self.assertIn("--manifest=", text)
        self.assertIn("guix archive --generate-key", text)
        self.assertIn("guix archive --export", text)
        self.assertIn("gh release create", text)
        self.assertIn("gh release download", text)
        self.assertIn("sha256sum -c SHA256SUMS", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("actions/upload-artifact", text)
        self.assertNotIn("if: ${{ false }}", text)

    def test_archive_workflow_validates_package_input_without_shell_interpolation(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("PACKAGES: ${{ inputs.packages || '' }}", text)
        self.assertIn('read -r -a PACKAGE_ARRAY <<< "$PACKAGES"', text)
        self.assertIn('case " $ALLOWED " in', text)
        self.assertNotIn("for package in ${{ inputs.packages", text)


if __name__ == "__main__":
    unittest.main()
