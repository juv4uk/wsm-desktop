# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass specifications must describe the channels we actually pin."""

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
        # One implementation of "is this Scheme balanced" lives in
        # scripts/check_scheme_syntax.py, which the fast checks already run over
        # every .scm in the tree. A local copy drifted from it once: this helper
        # counted the paren in a character literal like #\( and reported a
        # balanced file as broken.
        checker.scan(SPECS, self.text)

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

    def test_it_uses_the_pinned_guix_image_job_api(self) -> None:
        """The Guix lock exports image->job and arguments->systems from gnu ci."""
        self.assertIn(
            "#:use-module ((gnu ci) #:select (arguments->systems image->job))",
            self.text,
        )
        self.assertIn("(image->job store image", self.text)
        self.assertNotIn("derivation->job", self.text)

    def test_the_module_is_outside_the_channel_namespace(self) -> None:
        """wsm/ is the channel API; a CI helper is not part of it."""
        self.assertFalse((ROOT / "wsm" / "ci").exists())
        self.assertIn("(ci cuirass images)", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def test_the_fragment_uses_the_pinned_cuirass_service_api(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("(gnu services cuirass)", text)
        self.assertNotIn("(gnu services ci)", text)
        self.assertIn('(local-file "ci/cuirass/specs.scm"', text)
        self.assertIn(
            "(specifications #~(load #$%wsm-cuirass-specs))", text
        )
        self.assertNotIn("(use-substitutes?", text)
        self.assertNotIn("(fallback? #t)", text)


class DocumentationTests(unittest.TestCase):
    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("не завантажує образ", text.lower())
        self.assertIn("не перевіряє інсталятор", text.lower())

    def test_the_document_admits_the_instance_never_ran(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("інстанс не запускався", text.lower())


class JobModulePathTests(unittest.TestCase):
    """A custom job's module name must match its path under the channel root.

    A channel declared without `directory` resolves `(name sub module)` to
    <checkout>/<name>/sub/module.scm. A job module that declares a name its path
    cannot produce fails at load time, not at build time — and a spec that only
    checked for the string would not notice.
    """

    def test_the_module_name_matches_the_file_path(self) -> None:
        module = ROOT / "ci" / "cuirass" / "images.scm"
        declared = None
        for line in module.read_text(encoding="utf-8").splitlines():
            if line.startswith("(define-module "):
                declared = line.split("(define-module ", 1)[1].strip()
                break
        self.assertIsNotNone(declared, "images.scm declares no module")
        relative = module.relative_to(ROOT).with_suffix("")
        expected = "(" + " ".join(relative.parts) + ")"
        self.assertEqual(declared, expected)

    def test_the_specification_asks_for_the_name_the_file_declares(self) -> None:
        spec = (ROOT / "ci" / "cuirass" / "specs.scm").read_text(encoding="utf-8")
        module = (ROOT / "ci" / "cuirass" / "images.scm").read_text(encoding="utf-8")
        for line in module.splitlines():
            if line.startswith("(define-module "):
                declared = line.split("(define-module ", 1)[1].strip()
                break
        self.assertIn(f"(custom {declared})", spec)


if __name__ == "__main__":
    unittest.main()
