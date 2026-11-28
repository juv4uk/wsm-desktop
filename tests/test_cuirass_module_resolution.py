# SPDX-License-Identifier: LicenseRef-Volnist
"""The Cuirass custom job module must resolve from its repository path."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "ci" / "cuirass" / "images.scm"
SPECS = ROOT / "ci" / "cuirass" / "specs.scm"

MODULE_DECLARATION = re.compile(
    r"^\(define-module\s+\(([^)]+)\)", re.MULTILINE
)
CUSTOM_SELECTOR = re.compile(
    r"\(build\s+'\(custom\s+\(([^)]+)\)\)\)"
)


class CuirassModuleResolutionTests(unittest.TestCase):
    def test_image_module_name_matches_its_repository_path(self) -> None:
        source = IMAGES.read_text(encoding="utf-8")
        match = MODULE_DECLARATION.search(source)

        self.assertIsNotNone(match, "images.scm must declare a Guile module")
        module_parts = match.group(1).split()
        module_path = Path(*module_parts).with_suffix(".scm")

        self.assertEqual(module_path, IMAGES.relative_to(ROOT))
        self.assertNotEqual(
            module_parts[0],
            "wsm",
            "Cuirass helper modules must stay outside the public WSM namespace",
        )

    def test_custom_job_selector_matches_the_declared_module(self) -> None:
        source = IMAGES.read_text(encoding="utf-8")
        specs = SPECS.read_text(encoding="utf-8")
        module = MODULE_DECLARATION.search(source)
        selector = CUSTOM_SELECTOR.search(specs)

        self.assertIsNotNone(module, "images.scm must declare a Guile module")
        self.assertIsNotNone(selector, "Cuirass specs must declare a custom job module")
        self.assertEqual(selector.group(1), module.group(1))
        self.assertIn("#:use-module (gnu ci)", source)
        self.assertIn("#:use-module (guix grafts)", source)


if __name__ == "__main__":
    unittest.main()
