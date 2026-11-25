# SPDX-License-Identifier: GPL-3.0-or-later
"""Repository documentation checks."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs  # noqa: E402


class DocumentationTests(unittest.TestCase):
    def test_internal_markdown_links(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_docs.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DocumentationLanguageTests(unittest.TestCase):
    def test_ukrainian_detection(self) -> None:
        self.assertTrue(check_docs.is_ukrainian("Внесок у WSM Desktop"))
        self.assertFalse(check_docs.is_ukrainian("Contributing to WSM Desktop"))

    def test_ukrainian_detection_tolerates_technical_terms(self) -> None:
        body = "Документація ведеться українською; терміни Guix, Nix і Calamares не перекладаємо. " * 10
        self.assertTrue(check_docs.is_ukrainian(body))

    def test_translation_counterpart(self) -> None:
        self.assertEqual(
            check_docs.canonical_of(Path("docs/ETHICS.en.md")),
            Path("docs/ETHICS.md"),
        )
        self.assertEqual(
            check_docs.canonical_of(Path("CONTRIBUTING.en.md")),
            Path("CONTRIBUTING.md"),
        )
        self.assertIsNone(check_docs.canonical_of(Path("CONTRIBUTING.md")))


if __name__ == "__main__":
    unittest.main()
