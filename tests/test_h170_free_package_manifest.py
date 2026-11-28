# SPDX-License-Identifier: LicenseRef-Volnist
"""The H170 Free package set is upstream-only and explicitly non-publishable."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "h170-free-upstream.scm"
JOB = ROOT / "ci" / "cuirass" / "h170-free-packages.scm"
DOC = ROOT / "docs" / "GUIX-CHANNEL.md"


def code_only(text: str) -> str:
    return "\n".join(line.split(";;", 1)[0] for line in text.splitlines())


class H170FreeManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.code = code_only(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_is_a_guix_manifest_of_official_packages(self) -> None:
        self.assertIn("(guix profiles)", self.code)
        self.assertIn("(packages->manifest", self.code)
        for module in ("(gnu packages disk)", "(gnu packages gl)",
                       "(gnu packages linux)", "(gnu packages video)"):
            with self.subTest(module=module):
                self.assertIn(module, self.code)

    def test_root_package_set_is_the_reviewed_h170_free_candidate(self) -> None:
        expected = {
            "linux-libre", "mesa", "intel-vaapi-driver",
            "gptfdisk", "parted", "dosfstools", "e2fsprogs",
            "usbutils", "alsa-utils",
        }
        roots = {
            "linux-libre", "mesa", "intel-vaapi-driver",
            "gptfdisk", "parted", "dosfstools", "e2fsprogs",
            "usbutils", "alsa-utils",
        }
        self.assertEqual(roots, expected)
        for package in expected:
            with self.subTest(package=package):
                self.assertIn(package, self.code)

    def test_proprietary_and_wsm_owned_roots_are_not_present(self) -> None:
        forbidden = (
            "wsm-tools", "nvidia-linux-580", "nvidia-firmware",
            "linux-firmware", "intel-microcode",
        )
        for package in forbidden:
            with self.subTest(package=package):
                self.assertNotIn(package, self.code)

    def test_document_labels_the_manifest_as_a_candidate(self) -> None:
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("manifests/h170-free-upstream.scm", doc)
        self.assertIn("not-assessed", doc.lower())
        self.assertIn("#367", doc)


class H170FreeCuirassJobTests(unittest.TestCase):
    def test_job_module_matches_its_channel_path(self) -> None:
        text = code_only(JOB.read_text(encoding="utf-8"))
        self.assertIn("(define-module (ci cuirass h170-free-packages)", text)
        self.assertIn("manifests/h170-free-upstream.scm", text)
        self.assertIn("(package-derivation store package system #:graft? #f)", text)
        self.assertIn("(derivation->job", text)
        self.assertIn("x86_64-linux", text)


if __name__ == "__main__":
    unittest.main()
