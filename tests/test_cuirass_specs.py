# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass specifications must describe the channels we actually pin."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "ci" / "cuirass" / "specs.scm"
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SERVICE = ROOT / "ci" / "cuirass" / "service.scm"
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
        """A CI that floats is a CI that reports on a different tree."""
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertEqual(self.text.count(f'"{commit}"'), 2)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_the_wsm_channel_points_at_this_repository(self) -> None:
        self.assertEqual(self.text.count("https://github.com/juv4uk/wsm-desktop"), 2)


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")

    def test_the_module_exports_the_entry_point(self) -> None:
        self.assertIn("#:export (cuirass-jobs))", self.text)

    def test_it_builds_the_same_profile_the_release_builds(self) -> None:
        self.assertIn("systems/live-minimal.scm", self.text)

    def test_grafting_is_disabled(self) -> None:
        """Grafting belongs on the user's machine, not in a build farm."""
        self.assertIn("(%graft? #f)", self.text)

    def test_the_module_path_matches_its_declared_name(self) -> None:
        """Guile resolves module names from paths relative to the load root."""
        self.assertFalse((ROOT / "wsm" / "ci").exists())
        module = re.search(r"\\(define-module\\s+\\(([^)]+)\\)", self.text)
        self.assertIsNotNone(module)
        module_path = ROOT.joinpath(*module.group(1).split()).with_suffix(".scm")
        self.assertEqual(module_path, IMAGES)
        self.assertIn("(ci cuirass images)", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def test_the_fragment_uses_substitutes(self) -> None:
        """Without substitutes a build farm rebuilds every closure from source."""
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("(gnu services cuirass)", text)
        self.assertNotIn("(gnu services ci)", text)
        self.assertNotIn("(use-substitutes? #t)", text)
        self.assertIn('(local-file "specs.scm"', text)
        self.assertIn("cuirass-service-type", text)


class DocumentationTests(unittest.TestCase):
    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("не завантажує образ", text.lower())
        self.assertIn("не перевіряє інсталятор", text.lower())
        self.assertIn("--port=8081", text)
        self.assertIn("--listen=localhost", text)
        self.assertIn("не налаштована", text.lower())

    def test_the_document_admits_the_instance_never_ran(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("інстанс не запускався", text.lower())


if __name__ == "__main__":
    unittest.main()
