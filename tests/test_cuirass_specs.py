# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass definitions must match pinned Guix and fail closed pre-Phase-B."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_scheme_syntax as checker  # noqa: E402

SPECS = ROOT / "ci" / "cuirass" / "specs.scm"
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SERVICE = ROOT / "ci" / "cuirass" / "service.scm"
DOC = ROOT / "docs" / "CUIRASS.md"


def code_only(text: str) -> str:
    """Remove Scheme line comments before checking executable policy."""
    return "\n".join(line.split(";", 1)[0] for line in text.splitlines())


class CuirassTests(unittest.TestCase):
    def test_scheme_files_pass_the_shared_syntax_checker(self) -> None:
        for path in (SPECS, IMAGES, SERVICE):
            checker.scan(path, path.read_text(encoding="utf-8"))

    def test_no_merge_conflict_markers_remain(self) -> None:
        for path in (SPECS, IMAGES, SERVICE):
            text = path.read_text(encoding="utf-8")
            for marker in ("<<<<<<<", "=======", ">>>>>>>"):
                self.assertNotIn(marker, text, f"{marker} remains in {path}")

    def test_specification_is_one_custom_iso_job(self) -> None:
        code = code_only(SPECS.read_text(encoding="utf-8"))
        self.assertIn("(build '(custom (ci cuirass images)))", code)
        self.assertNotIn("(build '(channels wsm))", code)
        self.assertNotIn("wsm-tools", code)

    def test_specs_fail_closed_before_channel_phase_b(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        code = code_only(text)
        self.assertIn("NOT_REGISTERABLE", text)
        self.assertIn("OWNER_SIGNED_WSM_COMMIT_REQUIRED", code)
        self.assertNotIn('(branch "main")', code)
        self.assertNotIn("--disable-authentication", code)

    def test_official_guix_channel_is_pinned_and_introduced(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        match = re.search(r'\(commit "([0-9a-f]{40})"\)', lock)
        self.assertIsNotNone(match)
        self.assertIn(f'"{match.group(1)}"', text)
        self.assertIn("make-channel-introduction", text)

    def test_custom_module_path_and_selector_match(self) -> None:
        text = code_only(SPECS.read_text(encoding="utf-8"))
        self.assertIn("(define-module (ci cuirass images)", code_only(
            IMAGES.read_text(encoding="utf-8")))
        self.assertIn("(build '(custom (ci cuirass images)))", text)

    def test_custom_job_uses_pinned_iso_job_api(self) -> None:
        text = code_only(IMAGES.read_text(encoding="utf-8"))
        self.assertIn("(gnu ci)", text)
        self.assertIn("(gnu system image)", text)
        self.assertIn("(arguments->systems arguments)", text)
        self.assertIn("(image-with-os iso9660-image os)", text)
        self.assertIn("(image->job store image", text)
        self.assertIn('#:name "wsm-live-minimal-image"', text)
        self.assertNotIn("operating-system-image", text)
        self.assertNotIn("derivation->job", text)

    def test_profile_is_loaded_from_the_checked_out_channel(self) -> None:
        text = code_only(IMAGES.read_text(encoding="utf-8"))
        self.assertIn('search-path %load-path "systems/live-minimal.scm"', text)
        self.assertIn("(primitive-load profile)", text)

    def test_host_service_uses_pinned_api_and_root_relative_file(self) -> None:
        text = code_only(SERVICE.read_text(encoding="utf-8"))
        self.assertIn("(gnu services cuirass)", text)
        self.assertNotIn("(gnu services ci)", text)
        self.assertIn('(local-file "ci/cuirass/specs.scm"', text)
        self.assertIn('#~(load #$%wsm-cuirass-specs-file)', text)
        self.assertIn('(host "localhost")', text)
        self.assertIn("(port 8081)", text)
        self.assertNotIn("use-substitutes?", text)

    def test_guix_workflow_runs_for_cuirass_source_changes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "guix-profile-evaluation.yml")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn('"ci/cuirass/**/*.scm"', text)

    def test_document_preserves_acceptance_and_publication_boundaries(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("not_registerable", text)
        self.assertIn("not_run", text)
        self.assertIn("не завантажує образ", text)
        self.assertIn("не перевіряє інсталятор", text)
        self.assertIn("#367", text)
        self.assertIn("guix publish", text)


if __name__ == "__main__":
    unittest.main()
