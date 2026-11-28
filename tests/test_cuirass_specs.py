# SPDX-License-Identifier: LicenseRef-Volnist
"""Cuirass prototype files must match the pinned Guix API and stay inert."""

from __future__ import annotations

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


class CuirassPrototypeTests(unittest.TestCase):
    def test_all_scheme_fragments_are_balanced(self) -> None:
        for path in (SPECS, IMAGES, SERVICE):
            with self.subTest(path=path):
                self.assertTrue(balanced(path.read_text(encoding="utf-8")))

    def test_specs_file_is_one_list_form(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        code = [
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith(";")
        ]
        self.assertTrue(code[0].startswith("(list"))

    def test_specs_include_both_explicit_job_targets(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        self.assertIn('(name "wsm-tools")', text)
        self.assertIn('(name "wsm-live-minimal-image")', text)
        self.assertIn("(custom (ci cuirass images))", text)

    def test_official_guix_channel_uses_the_release_lock_revision(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        import re
        commits = re.findall(r'\(commit "([0-9a-f]{40})"\)', lock)
        self.assertTrue(commits)
        self.assertIn(commits[0], text)
        self.assertIn("make-channel-introduction", text)

    def test_wsm_input_is_unbootstrapped_and_not_registerable_yet(self) -> None:
        text = SPECS.read_text(encoding="utf-8")
        wsm = text.split("(name 'wsm)", 1)[1]
        self.assertIn('(branch "main")', wsm)
        self.assertNotIn("make-channel-introduction", wsm)
        self.assertIn("do not register", text.lower())
        self.assertIn("issue #367", text.lower())

    def test_custom_module_path_matches_the_declared_module_name(self) -> None:
        text = IMAGES.read_text(encoding="utf-8")
        self.assertIn("(define-module (ci cuirass images)", text)
        self.assertIn("#:use-module (gnu ci)", text)
        self.assertIn("derivation->job", text)
        self.assertIn("(custom (ci cuirass images))", SPECS.read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "wsm" / "ci").exists())

    def test_custom_module_exports_cuirass_entry_point(self) -> None:
        text = IMAGES.read_text(encoding="utf-8")
        self.assertIn("#:export (cuirass-jobs)", text)
        self.assertIn("systems/live-minimal.scm", text)
        self.assertIn("(%graft? #f)", text)

    def test_service_uses_the_pinned_guix_module_and_record_fields(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("(gnu services cuirass)", text)
        self.assertNotIn("(gnu services ci)", text)
        self.assertNotIn("(use-substitutes?", text)
        self.assertIn("(fallback? #f)", text)
        self.assertIn('(host "localhost")', text)
        self.assertIn('(port 8081)', text)

    def test_service_closes_over_the_actual_specs_file(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn('(local-file "ci/cuirass/specs.scm"', text)
        self.assertIn("(specifications #~(load #$%wsm-cuirass-specs))", text)

    def test_service_is_not_a_substitute_server(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("does not expose a substitute server", text)
        self.assertNotIn("guix publish --", text)

    def test_docs_block_registration_until_owner_trust_and_license_gates(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("не виконуйте", text)
        self.assertIn("owner phase b", text)
        self.assertIn("#367", text)
        self.assertIn("guix git authenticate", text)

    def test_docs_separate_cuirass_builds_from_guix_publish(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("guix publish", text)
        self.assertIn("не налаштований", text)
        self.assertNotIn("віддає результати як substitutes", text)

    def test_docs_keep_instance_status_not_run(self) -> None:
        text = DOC.read_text(encoding="utf-8").lower()
        self.assertIn("not_run", text)
        self.assertIn("не розгортався", text)


if __name__ == "__main__":
    unittest.main()
