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


class CanonicalDocumentationLanguageGateTests(unittest.TestCase):
    """A document under docs/ is Ukrainian, or it is a *.en.md translation."""

    def test_ukrainian_document_is_dominant(self) -> None:
        text = (
            "Це український текст із технічними термінами: sysfs, EDID, guix graph. "
            "Він містить багато латинських слів, але все одно є українським."
        )
        self.assertTrue(check_docs.is_ukrainian_dominant(text))

    def test_english_document_is_not_dominant(self) -> None:
        text = (
            "This document is written in English and mentions sysfs, EDID and guix "
            "graph, with almost no Cyrillic at all."
        )
        self.assertFalse(check_docs.is_ukrainian_dominant(text))

    def test_symbol_only_document_is_not_judged(self) -> None:
        self.assertTrue(check_docs.is_ukrainian_dominant("|---|---|\n| 1 | 2 |\n"))

    def test_every_canonical_document_passes_the_rule(self) -> None:
        self.assertEqual(check_docs.check_docs_language(), [])


class InstallerDocumentationPolicyTests(unittest.TestCase):
    def test_installer_doc_requires_three_selectable_frontends(self) -> None:
        document = (ROOT / "docs" / "INSTALLER.md").read_text(encoding="utf-8")
        self.assertIn("wsm-install-live", document)
        self.assertIn("Консольний CLI", document)
        self.assertIn("Псевдографічний TUI", document)
        self.assertIn("Графічний Calamares", document)
        self.assertIn("WSM Installer Selector", document)
        self.assertIn("Основний універсальний Live Installer", document)
        self.assertIn("Цільовий workflow графічного Calamares", document)
        self.assertIn("У поточних RC APPLY вимкнено", document)
        self.assertNotIn("Calamares — deprioritized/reference-only", document)


class DocumentationEntryPointLanguageTests(unittest.TestCase):
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
