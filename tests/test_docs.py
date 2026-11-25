# SPDX-License-Identifier: LicenseRef-Volnist
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
        self.assertTrue(
            check_docs.is_ukrainian(
                "Внесок у WSM Desktop. Дякуємо за інтерес до проєкту; "
                "найцінніший внесок зараз — перевірювані технічні дослідження."
            )
        )
        self.assertFalse(check_docs.is_ukrainian("Contributing to WSM Desktop"))

    def test_ukrainian_detection_rejects_a_mixed_heading(self) -> None:
        # A short heading dominated by a proper name is not a Ukrainian document.
        # Pinning the boundary keeps a future relaxation visible as a decision.
        self.assertFalse(check_docs.is_ukrainian("Внесок у WSM Desktop"))

    def test_ukrainian_detection_tolerates_technical_terms(self) -> None:
        body = "Документація ведеться українською; терміни Guix, Nix і Calamares не перекладаємо. " * 10
        self.assertTrue(check_docs.is_ukrainian(body))

    def test_english_text_with_a_ukrainian_fragment_is_not_ukrainian(self) -> None:
        english = (
            "This is the English documentation for setup, contribution, and security. " * 4
            + "Українська"
        )
        self.assertFalse(check_docs.is_ukrainian(english))

    def test_canonical_entry_points_are_dominantly_ukrainian(self) -> None:
        for relative in check_docs.ENTRY_POINT_DOCUMENTS:
            with self.subTest(path=relative):
                content = (ROOT / relative).read_text(encoding="utf-8")
                self.assertTrue(check_docs.is_ukrainian(content))

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
