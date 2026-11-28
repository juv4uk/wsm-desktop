# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass specifications must match the API the manuals describe."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "ci" / "cuirass" / "specs.scm"
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SERVICE = ROOT / "ci" / "cuirass" / "service.scm"
DOC = ROOT / "docs" / "CUIRASS.md"


def code_only(text: str) -> str:
    """Drop `;;' comments so a rule about code is not satisfied by prose."""
    return "\n".join(
        line.split(";")[0] for line in text.splitlines()
    )


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
        self.text = code_only(SPECS.read_text(encoding="utf-8"))

    def test_the_file_is_balanced(self) -> None:
        self.assertTrue(balanced(self.text))

    def test_the_last_expression_is_a_plain_list(self) -> None:
        """`cuirass register' loads the file and takes the list; a gexp is not it."""
        code = [line for line in self.text.splitlines()
                if line.strip() and not line.strip().startswith(";")]
        self.assertTrue(any(line.startswith("(list") for line in code))
        self.assertNotIn("#~(list", self.text)

    def test_names_are_symbols_as_the_manual_shows(self) -> None:
        self.assertIn("(name 'wsm-channel)", self.text)
        self.assertIn("(name 'wsm-live-minimal-image)", self.text)

    def test_the_channel_job_is_the_canonical_one(self) -> None:
        self.assertIn("(build '(channels wsm))", self.text)

    def test_the_custom_job_names_a_resolvable_module(self) -> None:
        """Cuirass resolves the module through the channel root, so the file
        path and the namespace must agree: ci/cuirass/images.scm."""
        self.assertIn("(build '(custom (ci cuirass images)))", self.text)
        self.assertTrue((ROOT / "ci" / "cuirass" / "images.scm").is_file())

    def test_the_guix_channel_is_pinned_to_the_release_commit(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertIn(f'"{commit}"', self.text)
        self.assertIn("make-channel-introduction", self.text)


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = code_only(IMAGES.read_text(encoding="utf-8"))

    def test_the_module_namespace_matches_its_path(self) -> None:
        self.assertIn("(define-module (ci cuirass images)", self.text)

    def test_it_uses_system_image_not_a_procedure_that_does_not_exist(self) -> None:
        """`operating-system-image' is not in gnu/system/image.scm."""
        self.assertIn("(system-image image)", self.text)
        self.assertNotIn("operating-system-image", self.text)

    def test_it_reads_the_systems_key_cuirass_actually_passes(self) -> None:
        self.assertIn("'systems", self.text)
        self.assertNotIn("'system)", self.text)

    def test_it_lowers_in_a_monadic_store(self) -> None:
        self.assertIn("run-with-store", self.text)
        self.assertIn("lower-object", self.text)
        self.assertIn("(guix monads)", self.text)

    def test_it_builds_the_same_profile_the_release_builds(self) -> None:
        self.assertIn("systems/live-minimal.scm", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = code_only(SERVICE.read_text(encoding="utf-8"))

    def test_the_service_type_comes_from_the_right_module(self) -> None:
        self.assertIn("(gnu services cuirass)", self.text)
        self.assertNotIn("(gnu services ci)", self.text)

    def test_no_field_the_record_does_not_have(self) -> None:
        self.assertNotIn("use-substitutes?", self.text)

    def test_specifications_are_inlined_not_loaded_from_a_runtime_path(self) -> None:
        """The gexp is evaluated in a build sandbox; /run/current-system is not there."""
        self.assertIn("#~(list", self.text)
        self.assertNotIn("/run/current-system/profile/share", self.text)


class DocumentationTests(unittest.TestCase):
    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("не завантажує образ", text.lower())
        self.assertIn("не перевіряє інсталятор", text.lower())

    def test_the_document_separates_running_instance_from_proven_build(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("реальний інстанс", text)
        self.assertIn("а не доказ складання", text)


if __name__ == "__main__":
    unittest.main()
