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
        scheme = SCHEME.read_text(encoding="utf-8")
        code = "\n".join(line.split(";;", 1)[0] for line in scheme.splitlines()).lower()
        self.assertNotIn("nonguix", code)
        self.assertNotIn("nvidia-firmware", code)
        self.assertNotIn("firmware-nvidia", code)
        self.assertNotIn("nvidia-kernel", code)

    def test_ci_builds_the_exact_locked_package_without_exporting_it(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "guix-profile-evaluation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("guix time-machine -C channels.lock.scm -- build", workflow)
        self.assertIn("linux-libre-h170", workflow)
        self.assertIn("PACKAGE_EXPR='(@ (wsm packages linux-libre) linux-libre-h170)'", workflow)
        self.assertIn('--expression="$PACKAGE_EXPR"', workflow)
        self.assertIn("guix hash --recursive --format=hex", workflow)
        self.assertNotIn("guix archive --export", workflow)
        self.assertNotIn("guix publish", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)

    def test_release_workflow_is_pinned_to_the_h170_kernel_and_provides_source(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "h170-gp107-release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('GITHUB_EVENT_NAME" != "workflow_dispatch', workflow)
        self.assertIn('GITHUB_REF" != "refs/heads/main', workflow)
        self.assertNotIn('publish/h170-gp107/**', workflow)
        self.assertIn("PACKAGE_EXPR='(@ (wsm packages linux-libre) linux-libre-h170)'", workflow)
        self.assertIn('--expression="$PACKAGE_EXPR"', workflow)
        self.assertIn('channels.lock.scm', workflow)
        self.assertIn('linux-libre-h170', workflow)
        self.assertIn('guix archive --generate-key', workflow)
        self.assertIn('guix archive --export --recursive "$STORE_PATH"', workflow)
        self.assertIn('guix time-machine -C channels.lock.scm -- hash --recursive', workflow)
        self.assertIn('actions/attest@v4', workflow)
        self.assertIn('closure.paths.txt', workflow)
        self.assertIn('derivation', workflow.lower())
        self.assertIn('linux-libre-h170-source.tar.xz', workflow)
        self.assertIn('signing-key.pub', workflow)
        self.assertIn('gh release create', workflow)
        self.assertIn('gh release download', workflow)
        self.assertIn('sha256sum -c SHA256SUMS', workflow)
        self.assertNotIn('secrets.GUIX_SIGNING_KEY', workflow)
        self.assertNotIn('actions/upload-artifact', workflow)
        # Negative dependency checks belong to the actual Scheme package
        # definition above. Release notes may correctly state that these inputs
        # are excluded; mentioning an excluded dependency is not adding it.
        self.assertIn('No NVIDIA firmware, proprietary driver, Nonguix package, or firmware blob is included.', workflow)
        self.assertNotIn('channels/compatibility.lock.scm', workflow)

    def test_documentation_keeps_runtime_and_compute_claims_unproven(self) -> None:
        text = MATRIX.read_text(encoding="utf-8").lower()
        self.assertIn("linux-libre-h170", text)
        self.assertIn("не доводить", text)
        self.assertIn("fecs", text)


if __name__ == "__main__":
    unittest.main()
