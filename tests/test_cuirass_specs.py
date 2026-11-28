# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass specifications must describe the channels we actually use."""

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

    def test_the_guix_channel_is_pinned_to_the_release_commit(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertEqual(self.text.count(f'"{commit}"'), 2)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_the_wsm_input_is_declared_as_a_tracking_branch(self) -> None:
        self.assertEqual(self.text.count('(branch "main")'), 2)
        self.assertIn("not an immutable release input", self.text.lower())


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")

    def test_the_module_exports_the_entry_point(self) -> None:
        self.assertIn("#:export (cuirass-jobs))", self.text)

    def test_it_builds_the_same_profile_the_release_builds(self) -> None:
        self.assertIn("systems/live-minimal.scm", self.text)

    def test_it_uses_the_image_helper_from_the_pinned_guix(self) -> None:
        self.assertIn("(gnu ci)", self.text)
        self.assertIn("(gnu image)", self.text)
        self.assertIn("(gnu system image)", self.text)
        self.assertIn("(image->job store", self.text)
        self.assertIn("(inherit iso9660-image)", self.text)
        self.assertIn("(operating-system os)", self.text)
        self.assertNotIn("operating-system-image", self.text)

    def test_it_resolves_the_profile_from_the_channel_load_path(self) -> None:
        self.assertIn("(search-path %load-path relative-path)", self.text)
        self.assertIn("(primitive-load (channel-file profile))", self.text)

    def test_the_module_is_outside_the_channel_namespace(self) -> None:
        self.assertFalse((ROOT / "wsm" / "ci").exists())
        self.assertIn("(ci cuirass images)", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SERVICE.read_text(encoding="utf-8")

    def test_it_imports_the_actual_guix_cuirass_service_module(self) -> None:
        self.assertIn("(gnu services cuirass)", self.text)
        self.assertNotIn("(gnu services ci)", self.text)

    def test_it_loads_specs_from_the_service_source_tree(self) -> None:
        self.assertIn("(dirname (current-filename))", self.text)
        self.assertIn('(local-file %wsm-cuirass-specs-path "wsm-cuirass-specs.scm")', self.text)
        self.assertIn("#~(load #$%wsm-cuirass-specs-file)", self.text)
        self.assertNotIn("/run/current-system/profile/share/wsm/ci/cuirass/specs.scm", self.text)

    def test_it_does_not_use_an_unknown_substitutes_field(self) -> None:
        self.assertNotIn("use-substitutes?", self.text)
        self.assertIn("(fallback? #t)", self.text)

    def test_service_is_loopback_only_and_does_not_claim_to_publish(self) -> None:
        self.assertIn('(host "localhost")', self.text)
        self.assertIn("does not publish its build results as substitutes", self.text.lower())


class DocumentationTests(unittest.TestCase):
    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("не завантажує образ", text.lower())
        self.assertIn("не перевіряє інсталятор", text.lower())

    def test_the_document_admits_the_instance_never_ran(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("інстанс не запускався", text.lower())

    def test_it_does_not_claim_local_cuirass_publishes_substitutes(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("не публікує substitutes", text)
        self.assertIn("guix publish", text)
        self.assertIn("phase b", text)


class JobModulePathTests(unittest.TestCase):
    """A custom job's module name must match its path under the channel root."""

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
        spec = SPECS.read_text(encoding="utf-8")
        module = IMAGES.read_text(encoding="utf-8")
        for line in module.splitlines():
            if line.startswith("(define-module "):
                declared = line.split("(define-module ", 1)[1].strip()
                break
        self.assertIn(f"(custom {declared})", spec)


if __name__ == "__main__":
    unittest.main()
