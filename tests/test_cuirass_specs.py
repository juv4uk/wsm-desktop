# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass definitions must match the pinned Guix APIs and trust boundaries."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_scheme_syntax as checker  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "ci" / "cuirass" / "specs.scm"
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SERVICE = ROOT / "ci" / "cuirass" / "service.scm"
DOC = ROOT / "docs" / "CUIRASS.md"


class SpecsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SPECS.read_text(encoding="utf-8")

    def test_the_file_is_balanced(self) -> None:
        checker.scan(SPECS, self.text)

    def test_it_is_a_single_list_form(self) -> None:
        code = [line for line in self.text.splitlines()
                if line.strip() and not line.strip().startswith(";")]
        self.assertTrue(code[0].startswith("(list"))

    def test_both_jobs_are_declared(self) -> None:
        self.assertIn('(name "wsm-tools")', self.text)
        self.assertIn('(name "wsm-live-minimal-image")', self.text)

    def test_the_guix_channel_matches_the_release_lock(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock)
        self.assertIsNotNone(commit)
        self.assertEqual(self.text.count(f'"{commit.group(1)}"'), 2)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_wsm_is_a_tracking_development_input_not_a_release_pin(self) -> None:
        self.assertEqual(self.text.count("https://github.com/juv4uk/wsm-desktop"), 2)
        self.assertEqual(self.text.count('(branch "main")'), 2)
        self.assertIn("resolved commit", self.text)
        self.assertIn("immutable", self.text)

    def test_custom_selector_matches_the_module_path(self) -> None:
        self.assertIn("(build '(custom (ci cuirass images)))", self.text)


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")

    def test_module_name_matches_repository_path(self) -> None:
        module = re.search(r"\(define-module\s+\(([^)]+)\)", self.text)
        self.assertIsNotNone(module)
        module_path = ROOT.joinpath(*module.group(1).split()).with_suffix(".scm")
        self.assertEqual(module_path, IMAGES)

    def test_imports_the_pinned_cuirass_and_image_apis(self) -> None:
        self.assertIn(
            "((gnu ci) #:select (arguments->systems image->job))", self.text
        )
        self.assertIn(
            "((gnu system image) #:select (image-with-os iso9660-image))",
            self.text,
        )
        self.assertNotIn("operating-system-image", self.text)
        self.assertNotRegex(self.text, r"\(\s*derivation->job\b")

    def test_uses_cuirass_system_argument_and_release_architecture(self) -> None:
        self.assertIn("(arguments->systems arguments)", self.text)
        self.assertIn('"x86_64-linux"', self.text)
        self.assertIn("(filter", self.text)

    def test_loads_profile_from_the_checked_out_channel(self) -> None:
        self.assertIn(
            'search-path %load-path "systems/live-minimal.scm"', self.text
        )
        self.assertIn("(primitive-load profile)", self.text)

    def test_job_uses_the_release_iso_type_and_public_constructor(self) -> None:
        self.assertIn("(image-with-os iso9660-image os)", self.text)
        self.assertIn("(image->job store image", self.text)
        self.assertIn('#:name "wsm-live-minimal-image"', self.text)
        self.assertIn('#:system system', self.text)


class ServiceFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SERVICE.read_text(encoding="utf-8")

    def test_uses_the_pinned_cuirass_service_module(self) -> None:
        self.assertIn("(gnu services cuirass)", self.text)
        self.assertNotIn("(gnu services ci)", self.text)

    def test_uses_only_existing_pinned_configuration_fields(self) -> None:
        self.assertIn("(fallback? #t)", self.text)
        self.assertIn("(specifications %wsm-cuirass-specs)", self.text)
        self.assertNotRegex(self.text, r"\(\s*use-substitutes\?")

    def test_spec_file_is_captured_relative_to_this_source_file(self) -> None:
        self.assertIn('(local-file "specs.scm" "wsm-cuirass-specs.scm")',
                      self.text)
        self.assertIn("#~(load #$%wsm-cuirass-specs-file)", self.text)

    def test_web_service_is_loopback_only(self) -> None:
        self.assertIn('(host "localhost")', self.text)
        self.assertIn("(port 8081)", self.text)


class DocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8").lower()

    def test_instance_and_jobs_are_honestly_not_run(self) -> None:
        self.assertIn("not_run", self.text)
        self.assertIn("жоден cuirass job не запускалися", self.text)

    def test_channel_phase_b_is_a_prerequisite(self) -> None:
        self.assertIn("phase b", self.text)
        self.assertIn("guix git authenticate", self.text)
        self.assertIn("--disable-authentication", self.text)

    def test_does_not_claim_public_substitute_distribution(self) -> None:
        self.assertIn("не публікує", self.text)
        self.assertIn("guix publish", self.text)
        self.assertIn("#367", self.text)

    def test_distinguishes_build_from_boot_and_installer_acceptance(self) -> None:
        self.assertIn("не завантажує", self.text)
        self.assertIn("не перевіряє інсталятор", self.text)
        self.assertIn("bios", self.text)
        self.assertIn("uefi", self.text)


if __name__ == "__main__":
    unittest.main()
