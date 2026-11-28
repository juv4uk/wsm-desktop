# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass templates must match the pinned Guix API and fail closed pre-Phase-B."""

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

    def test_scheme_syntax_uses_the_shared_checker(self) -> None:
        checker.scan(SPECS, self.text)

    def test_it_is_a_single_list_form(self) -> None:
        code = [line for line in self.text.splitlines()
                if line.strip() and not line.strip().startswith(";;")]
        self.assertTrue(code[0].startswith("(list"))

    def test_both_allowlisted_jobs_are_declared(self) -> None:
        self.assertIn('(name "wsm-tools")', self.text)
        self.assertIn('(name "wsm-live-minimal-image")', self.text)
        self.assertNotIn("(build '(channels wsm))", self.text)

    def test_guix_channel_is_pinned_to_the_free_release_commit(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        commit = re.search(r'\(commit "([0-9a-f]{40})"\)', lock).group(1)
        self.assertEqual(self.text.count(f'"{commit}"'), 2)

    def test_wsm_channel_is_explicitly_not_registerable_before_phase_b(self) -> None:
        self.assertIn("NOT_REGISTERABLE", self.text)
        self.assertEqual(
            self.text.count('"OWNER_SIGNED_WSM_COMMIT_REQUIRED"'), 2
        )
        self.assertNotIn('(branch "main")', self.text)
        self.assertNotIn("--disable-authentication", self.text)

    def test_official_channel_keeps_its_introduction(self) -> None:
        self.assertEqual(self.text.count("make-channel-introduction"), 2)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_wsm_channel_points_at_this_repository(self) -> None:
        self.assertEqual(
            self.text.count("https://github.com/juv4uk/wsm-desktop"), 2
        )


class JobModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = IMAGES.read_text(encoding="utf-8")

    def test_module_name_matches_its_real_channel_path(self) -> None:
        match = re.search(r'\(define-module\s+\(([^)]+)\)', self.text)
        self.assertIsNotNone(match)
        module_path = Path(*match.group(1).split()).with_suffix(".scm")
        self.assertEqual(
            module_path.as_posix(),
            IMAGES.relative_to(ROOT).as_posix(),
        )

    def test_custom_selector_uses_the_same_module_name(self) -> None:
        self.assertIn(
            "(build '(custom (ci cuirass images)))",
            SPECS.read_text(encoding="utf-8"),
        )

    def test_uses_the_pinned_guix_cuirass_job_api(self) -> None:
        self.assertIn("(gnu ci)", self.text)
        self.assertIn("(arguments->systems arguments)", self.text)
        self.assertIn("(image->job store image", self.text)
        self.assertIn("(image-with-os iso9660-image os)", self.text)
        self.assertNotIn("operating-system-image", self.text)
        self.assertNotIn("(guix derivations)", self.text)
        self.assertNotIn("derivation->job", self.text)

    def test_profile_is_resolved_from_the_checked_out_channel(self) -> None:
        self.assertIn('search-path %load-path "systems/live-minimal.scm"', self.text)
        self.assertIn("(primitive-load profile)", self.text)

    def test_image_helper_owns_derivation_and_graft_policy(self) -> None:
        # The pinned Guix image->job helper calls system-image and disables grafts.
        self.assertIn("image->job", self.text)
        self.assertNotIn("(%graft? #f)", self.text)


class ServiceFragmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SERVICE.read_text(encoding="utf-8")

    def test_imports_the_real_pinned_guix_service_module(self) -> None:
        self.assertIn("(gnu services cuirass)", self.text)
        self.assertNotIn("(gnu services ci)", self.text)

    def test_does_not_use_removed_or_guessed_configuration_fields(self) -> None:
        self.assertNotIn("use-substitutes?", self.text)
        self.assertNotIn("/run/current-system/profile/share/wsm", self.text)
        self.assertIn("(specifications specifications)", self.text)

    def test_is_a_host_helper_not_a_desktop_service(self) -> None:
        self.assertIn("(define (wsm-cuirass-service specifications)", self.text)
        self.assertIn("(fallback? #t)", self.text)


class DocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8").lower()

    def test_the_document_states_what_cuirass_cannot_prove(self) -> None:
        self.assertIn("не завантажує образ", self.text)
        self.assertIn("не перевіряє інсталятор", self.text)

    def test_cuirass_is_not_claimed_registerable_before_phase_b(self) -> None:
        self.assertIn("not_registerable", self.text)
        self.assertIn("phase b", self.text)
        self.assertIn("публічне substitute serving не дозволене", self.text)
        self.assertIn("окремий guix publish", self.text)

    def test_the_document_admits_the_instance_never_ran(self) -> None:
        self.assertIn("інстанс не запускався", self.text)


if __name__ == "__main__":
    unittest.main()
