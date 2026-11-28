# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free kernel overlay must remain a one-patch upstream derivative."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEME = ROOT / "wsm" / "packages" / "linux-libre.scm"
PATCH = ROOT / "wsm" / "packages" / "patches" / "linux-libre-h170-nouveau-atomic.patch"
MATRIX = ROOT / "docs" / "hardware" / "H170-FIRMWARE-MATRIX.md"


class H170LinuxLibreOverlayTests(unittest.TestCase):
    def test_patch_hunk_line_counts_match_the_unified_diff(self) -> None:
        patch = PATCH.read_text(encoding="utf-8").splitlines()
        hunk_re = re.compile(r"^@@ -(?:[0-9]+)(?:,([0-9]+))? \+(?:[0-9]+)(?:,([0-9]+))? @@")
        hunks = [index for index, line in enumerate(patch) if hunk_re.match(line)]
        self.assertTrue(hunks, "the upstream patch must contain unified-diff hunks")
        for position, start in enumerate(hunks):
            match = hunk_re.match(patch[start])
            assert match is not None
            expected_old = int(match.group(1) or "1")
            expected_new = int(match.group(2) or "1")
            end = hunks[position + 1] if position + 1 < len(hunks) else len(patch)
            old_count = 0
            new_count = 0
            for line in patch[start + 1:end]:
                if line == "-- ":
                    break
                if line.startswith(" "):
                    old_count += 1
                    new_count += 1
                elif line.startswith("-"):
                    old_count += 1
                elif line.startswith("+"):
                    new_count += 1
                elif line.startswith("\\"):
                    continue
                else:
                    break
            self.assertEqual(old_count, expected_old, f"old hunk count mismatch at line {start + 1}")
            self.assertEqual(new_count, expected_new, f"new hunk count mismatch at line {start + 1}")

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
        self.assertIn('(local-file "patches/linux-libre-h170-nouveau-atomic.patch"', scheme)
        self.assertNotIn("search-path %load-path", scheme)
        self.assertIn('(name "linux-libre-h170")', scheme)

    def test_overlay_does_not_add_proprietary_driver_or_firmware_packages(self) -> None:
        scheme = SCHEME.read_text(encoding="utf-8")
        code = "\n".join(line.split(";;", 1)[0] for line in scheme.splitlines()).lower()
        self.assertNotIn("nonguix", code)
        self.assertNotIn("nvidia-firmware", code)
        self.assertNotIn("firmware-nvidia", code)
        self.assertNotIn("nvidia-kernel", code)

    def test_guix_profile_evaluation_uses_authenticated_codeberg_transport(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "guix-profile-evaluation.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("https://codeberg.org/guix/guix.git", workflow)
        self.assertIn("https://git.guix.gnu.org/guix.git", workflow)
        self.assertNotIn("--disable-authentication", workflow)

    def test_profile_workflow_evaluates_without_exporting_binary_artifacts(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "guix-profile-evaluation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("make check-guix-eval", workflow)
        self.assertIn("WSM_CHANNEL_AUTHENTICATION=NOT_TESTED", workflow)
        self.assertNotIn("guix archive --export", workflow)
        self.assertNotIn("guix publish", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)

    def test_release_workflow_builds_and_publishes_a_verified_recursive_closure(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "h170-gp107-release.yml").read_text(
            encoding="utf-8"
        )
        import yaml

        data = yaml.load(workflow, Loader=yaml.BaseLoader)
        trigger = data["on"]["push"]
        self.assertEqual(trigger["branches"], ["main"])
        self.assertTrue({
            ".github/workflows/h170-gp107-release.yml",
            "channels.lock.scm",
            "wsm/packages/linux-libre.scm",
            "wsm/packages/patches/linux-libre-h170-nouveau-atomic.patch",
        }.issubset(set(trigger["paths"])))
        self.assertIn("Use the GNU Guix project's authenticated Codeberg mirror", workflow)
        self.assertIn("PACKAGE_EXPR='(@ (wsm packages linux-libre) linux-libre-h170)'", workflow)
        self.assertIn('DERIVATION_PATH=', workflow)
        self.assertIn('guix archive --export --recursive "$STORE_PATH"', workflow)
        self.assertIn('guix gc --requisites "$STORE_PATH"', workflow)
        self.assertIn('closure.paths.txt', workflow)
        self.assertIn('linux-libre-h170-source.tar.xz', workflow)
        self.assertIn('signing-key.pub', workflow)
        self.assertIn('provenance.json', workflow)
        self.assertIn('uses: actions/attest@v4', workflow)
        self.assertIn('gh release create', workflow)
        self.assertIn('--draft', workflow)
        self.assertIn('gh release download', workflow)
        self.assertIn('sha256sum -c SHA256SUMS', workflow)
        self.assertIn('gh release edit "$TAG" --draft=false', workflow)
        self.assertLess(
            workflow.index('gh release download'),
            workflow.index('gh release edit "$TAG" --draft=false'),
        )
        self.assertNotIn('secrets.GUIX_SIGNING_KEY', workflow)
        self.assertNotIn('actions/upload-artifact', workflow)
        self.assertIn('No NVIDIA firmware, proprietary driver, Nonguix package, or firmware blob is included.', workflow)
        self.assertNotIn('channels/compatibility.lock.scm', workflow)

    def test_documentation_keeps_runtime_and_compute_claims_unproven(self) -> None:
        text = MATRIX.read_text(encoding="utf-8").lower()
        self.assertIn("linux-libre-h170", text)
        self.assertIn("не доводить", text)
        self.assertIn("fecs", text)

    def test_the_package_describes_itself_rather_than_inheriting_upstream_text(self) -> None:
        """`guix show linux-libre-h170` must not read as plain upstream linux-libre."""
        scheme = SCHEME.read_text(encoding="utf-8")
        self.assertIn("(synopsis ", scheme)
        self.assertIn("(description", scheme)
        self.assertIn("H170 candidate", scheme)
        self.assertIn("ed7fb901fce3", scheme)

    def test_the_description_does_not_claim_what_the_patch_cannot_do(self) -> None:
        scheme = SCHEME.read_text(encoding="utf-8")
        # The description is wrapped across lines in the source, so compare it as
        # text rather than as lines.
        flat = " ".join(scheme.split())
        self.assertIn("FECS/GPCCS", flat)
        self.assertIn("not a statement that the kernel boots", flat)


if __name__ == "__main__":
    unittest.main()
