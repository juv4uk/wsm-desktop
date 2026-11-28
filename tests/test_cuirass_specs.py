# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass specifications must match the pinned Guix API and channel layout."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "ci" / "cuirass" / "specs.scm"
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SERVICE = ROOT / "ci" / "cuirass" / "service.scm"
PACKAGE = ROOT / "wsm" / "packages" / "wsm.scm"
DOC = ROOT / "docs" / "CUIRASS.md"


def balanced(text: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    comment = False
    for char in text:
        if char == "\n":
            comment = False
            continue
        if comment:
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == ";":
            comment = True
            continue
        if char == '"':
            in_string = True
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


class SpecsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SPECS.read_text(encoding="utf-8")

    def test_the_file_is_balanced(self) -> None:
        self.assertTrue(balanced(self.text))

    def test_it_is_a_single_list_form(self) -> None:
        code = [line for line in self.text.splitlines()
                if line.strip() and not line.strip().startswith(";")]
        self.assertTrue(code[0].startswith("(list"))

    def test_both_jobs_are_declared(self) -> None:
        self.assertIn('(name "wsm-tools")', self.text)
        self.assertIn('(name "wsm-live-minimal-image")', self.text)

    def test_the_guix_channel_is_pinned_to_the_release_commit(self) -> None:
        """Guix is pinned; WSM main intentionally remains a tracking input."""
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertEqual(self.text.count(f'"{commit}"'), 2)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_the_wsm_channel_is_a_tracking_development_input(self) -> None:
        self.assertEqual(self.text.count("https://github.com/juv4uk/wsm-desktop"), 2)
        self.assertEqual(self.text.count('(branch "main")'), 2)
        self.assertIn("NOT an immutable reproduction", self.text)


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")
        self.specs = SPECS.read_text(encoding="utf-8")

    def test_module_name_matches_repository_path_and_custom_selector(self) -> None:
        self.assertIn("(define-module (ci cuirass images)", self.text)
        self.assertIn("(build '(custom (ci cuirass images)))", self.specs)
        self.assertFalse((ROOT / "wsm" / "ci" / "images.scm").exists())

    def test_imports_the_pinned_cuirass_and_image_apis(self) -> None:
        self.assertIn("((gnu ci) #:select (arguments->systems image->job))", self.text)
        self.assertIn("((gnu system image) #:select (image-with-os iso9660-image))",
                      self.text)
        self.assertNotIn("operating-system-image", self.text)
        self.assertNotIn("derivation->job", self.text)

    def test_profile_is_resolved_from_channel_load_path(self) -> None:
        self.assertIn('search-path %load-path "systems/live-minimal.scm"', self.text)
        self.assertIn("(primitive-load profile)", self.text)

    def test_job_uses_the_release_iso_image_type(self) -> None:
        self.assertIn("(image-with-os iso9660-image", self.text)
        self.assertIn('#:name "wsm-live-minimal-image"', self.text)
        self.assertIn('#:system system', self.text)
        self.assertIn("(arguments->systems arguments)", self.text)

    def test_only_the_wsm_release_architecture_is_requested(self) -> None:
        self.assertIn('"x86_64-linux"', self.text)
        self.assertIn("Cuirass request does not include the WSM image system", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def test_service_load_path_is_installed_by_wsm_tools(self) -> None:
        service = SERVICE.read_text(encoding="utf-8")
        package = PACKAGE.read_text(encoding="utf-8")
        self.assertIn("/share/wsm/ci/cuirass/specs.scm", service)
        self.assertIn('"ci/cuirass/specs.scm"', package)
        self.assertIn('"/share/wsm/ci/cuirass"', package)
        self.assertIn("cuirass-service-type", service)
        self.assertIn("(use-substitutes? #t)", service)
        self.assertNotIn("guix publish", service)
        self.assertNotIn("publish?", service)


class DocumentationTests(unittest.TestCase):
    def test_document_states_the_acceptance_boundary(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("не завантажує образ", text)
        self.assertIn("не перевіряє інсталятор", text)
        self.assertIn("не публікує", text)

    def test_document_marks_registration_and_authentication_not_run(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("not_run", text)
        self.assertIn("phase b", text)
        self.assertIn("не вимикати автентифікацію", text)

    def test_document_distinguishes_tracking_channel_from_release_pin(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("main", text)
        self.assertIn("не є відтворенням релізу", text)


if __name__ == "__main__":
    unittest.main()
