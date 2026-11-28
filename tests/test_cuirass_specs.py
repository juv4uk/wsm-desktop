# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass prototype files must match the pinned Guix API and stay inert."""

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
        code = [
            line for line in self.text.splitlines()
            if line.strip() and not line.strip().startswith(";")
        ]
        self.assertTrue(code[0].startswith("(list"))

    def test_both_job_targets_are_declared(self) -> None:
        self.assertIn('(name "wsm-tools")', self.text)
        self.assertIn('(name "wsm-live-minimal-image")', self.text)
        self.assertIn("(build '(custom (ci cuirass images)))", self.text)

    def test_the_guix_channel_is_pinned_to_the_release_commit(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertEqual(self.text.count(f'"{commit}"'), 2)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_the_wsm_channel_is_explicitly_a_moving_unbootstrapped_input(self) -> None:
        self.assertEqual(self.text.count('https://github.com/juv4uk/wsm-desktop'), 2)
        self.assertIn('(branch "main")', self.text)
        self.assertIn("not an", self.text.lower())
        self.assertIn("do not register", self.text.lower())
        # The WSM channel must not be given a fabricated owner introduction.
        self.assertNotIn("(make-channel-introduction", self.text.split("(name 'wsm)", 1)[1])


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")

    def test_the_module_path_matches_the_scheme_name(self) -> None:
        self.assertIn("(define-module (ci cuirass images)", self.text)
        self.assertIn("#:use-module (gnu ci)", self.text)
        self.assertIn("derivation->job", self.text)
        self.assertFalse((ROOT / "wsm" / "ci").exists())

    def test_the_module_exports_the_entry_point(self) -> None:
        self.assertIn("#:export (cuirass-jobs))", self.text)

    def test_it_builds_the_release_profile(self) -> None:
        self.assertIn("systems/live-minimal.scm", self.text)

    def test_grafting_is_disabled(self) -> None:
        self.assertIn("(%graft? #f)", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SERVICE.read_text(encoding="utf-8")

    def test_service_module_matches_pinned_guix_source(self) -> None:
        self.assertIn("(gnu services cuirass)", self.text)
        self.assertNotIn("(gnu services ci)", self.text)

    def test_no_nonexistent_substitute_field_is_used(self) -> None:
        self.assertNotIn("(use-substitutes?", self.text)
        self.assertIn("(fallback? #f)", self.text)

    def test_specs_file_is_in_the_system_closure(self) -> None:
        self.assertIn('(local-file "ci/cuirass/specs.scm"', self.text)
        self.assertIn("(specifications #~(load #$%wsm-cuirass-specs))", self.text)

    def test_admin_listener_is_local_only(self) -> None:
        self.assertIn('(host "localhost")', self.text)
        self.assertIn('(port 8081)', self.text)


class DocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8").lower()

    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        self.assertIn("не завантажує образ", self.text)
        self.assertIn("не перевіряє інсталятор", self.text)

    def test_registration_is_blocked_until_trust_and_license_gates(self) -> None:
        self.assertIn("не реєструвати", self.text)
        self.assertIn("owner phase b", self.text)
        self.assertIn("#367", self.text)
        self.assertIn("guix git authenticate", self.text)

    def test_substitute_serving_is_a_separate_future_service(self) -> None:
        self.assertIn("guix publish", self.text)
        self.assertIn("не налаштований", self.text)
        self.assertNotIn("віддає результати як substitutes", self.text)

    def test_instance_is_explicitly_not_run(self) -> None:
        self.assertIn("not_run", self.text)
        self.assertIn("не розгортався", self.text)


if __name__ == "__main__":
    unittest.main()
