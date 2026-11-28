# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free package set must stay tied to owner hardware and fail-closed policy."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci" / "packages" / "h170-free.scm"
DOC = ROOT / "ci" / "packages" / "README.md"
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "h170-free-package-build-evidence.yml"
ARCHIVE_WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"
MAKEFILE = ROOT / "Makefile"
FREE_PROFILE = ROOT / "drivers" / "profiles" / "h170-free.json"
COMPAT_PROFILE = ROOT / "drivers" / "profiles" / "h170-compatibility.json"

EXPECTED_PACKAGES = {
    "linux-libre", "mesa", "mesa-utils", "vulkan-loader", "vulkan-tools",
    "intel-media-driver", "intel-vaapi-driver", "libva-utils", "igt-gpu-tools",
    "pciutils", "usbutils", "dmidecode", "lshw", "nvme-cli",
    "smartmontools", "alsa-utils", "util-linux", "e2fsprogs", "parted",
    "gptfdisk", "dosfstools", "iproute", "iw", "ethtool",
}

FORBIDDEN_PACKAGES = {
    "wsm-tools", "wsm-live-tools", "linux-firmware",
    "nvidia-driver", "nvidia", "nouveau-firmware",
}


def scheme_code(text: str) -> str:
    """Drop line comments before checking package identifiers."""
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


class H170FreePackageSetTests(unittest.TestCase):
    def test_manifest_uses_the_free_lock_and_official_package_modules(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("(guix profiles)", text)
        for module in (
            "(gnu packages linux)", "(gnu packages gl)",
            "(gnu packages vulkan)", "(gnu packages video)",
            "(gnu packages admin)", "(gnu packages disk)",
            "(gnu packages pciutils)", "(gnu packages networking)",
        ):
            with self.subTest(module=module):
                self.assertIn(module, text)
        self.assertNotIn("channels/compatibility.lock.scm", text)
        self.assertNotIn("nonguix", text.lower())

    def test_manifest_contains_the_curated_h170_package_roots(self) -> None:
        code = scheme_code(MANIFEST.read_text(encoding="utf-8"))
        for package in sorted(EXPECTED_PACKAGES):
            with self.subTest(package=package):
                self.assertRegex(code, rf"(?<![A-Za-z0-9_+-]){package}(?![A-Za-z0-9_+-])")

    def test_manifest_excludes_unapproved_wsm_and_proprietary_payloads(self) -> None:
        code = scheme_code(MANIFEST.read_text(encoding="utf-8"))
        for package in sorted(FORBIDDEN_PACKAGES):
            with self.subTest(package=package):
                self.assertNotRegex(code, rf"(?<![A-Za-z0-9_+-]){package}(?![A-Za-z0-9_+-])")

    def test_profile_facts_are_kept_in_the_canonical_hardware_manifest(self) -> None:
        free = json.loads(FREE_PROFILE.read_text(encoding="utf-8"))
        compat = json.loads(COMPAT_PROFILE.read_text(encoding="utf-8"))
        models = {item["model"] for item in free["devices"]}
        self.assertIn("Gigabyte H170-Gaming 3", models)
        self.assertIn("Intel Core i5-6400 (Skylake)", models)
        self.assertIn("Intel HD Graphics 530", models)
        self.assertIn("NVIDIA GeForce GTX 1050 Ti (Pascal, sm_61)", models)
        gpu = next(item for item in free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        self.assertIn("10de:1c82", gpu["pci_ids"])
        self.assertEqual(gpu["firmware"]["requirement"], "required")
        compat_gpu = next(item for item in compat["devices"] if item["device_id"] == "nvidia-gtx-1050-ti-compat")
        self.assertEqual(compat_gpu["package_resolution"], "not-assessed")

    def test_documentation_records_the_kms_and_firmware_limits(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("linux-libre 7.3.5", text)
        self.assertIn("atomic-kms", text)
        self.assertIn("fe cs", text.replace(" ", ""))
        self.assertIn("#367", text)
        self.assertIn("#586", text)
        self.assertIn("not-published", text)

    def test_manual_build_workflow_is_metadata_only(self) -> None:
        text = BUILD_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("channels.lock.scm", text)
        self.assertIn("ci/packages/h170-free.scm", text)
        self.assertIn("guix size --sort=closure", text)
        self.assertIn("guix hash --recursive", text)
        for forbidden in (
            "actions/upload-artifact", "guix archive --export",
            "gh release upload", "gh release create", "guix publish",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_binary_archive_workflow_remains_disabled(self) -> None:
        text = ARCHIVE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("if: \${{ false }}", text)
        self.assertNotIn("guix archive --export", text)
        self.assertNotIn("actions/upload-artifact", text)

    def test_make_targets_include_static_and_pinned_resolution_checks(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        check = next(line for line in text.splitlines() if line.startswith("check:"))
        self.assertIn("check-h170-package-set", check)
        self.assertIn("check-h170-package-set:", text)
        self.assertIn("tests/test_h170_package_set.py", text)
        guix_eval = text.split("check-guix-eval:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("ci/packages/h170-free.scm", guix_eval)
        self.assertIn("--dry-run", guix_eval)
        self.assertIn("build-h170-free-package-set:", text)

    def test_no_compatibility_package_is_smuggled_into_free(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("compatibility", text)
        self.assertIn("not part of free", text)
        self.assertIn("no nonguix", text)


if __name__ == "__main__":
    unittest.main()
