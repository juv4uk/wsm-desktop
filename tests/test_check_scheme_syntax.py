# SPDX-License-Identifier: LicenseRef-Volnist
"""Tests for scripts/check_scheme_syntax.py.

The checker exists so that a broken Scheme form fails in seconds instead of in the
Guix evaluation job. It is not a Scheme reader, so the tests pin what it must
ignore - strings, comments, datum comments, character literals - as carefully as
what it must catch.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_scheme_syntax as checker  # noqa: E402


def balanced(source: str) -> bool:
    try:
        checker.scan(Path("test.scm"), source)
    except checker.Imbalance:
        return False
    return True


class BalancedFormsTest(unittest.TestCase):
    def test_simple_form(self) -> None:
        self.assertTrue(balanced("(define x 1)"))

    def test_nested_forms(self) -> None:
        self.assertTrue(balanced("(define (f x) (list x [y] {z}))"))

    def test_empty_file(self) -> None:
        self.assertTrue(balanced(""))


class IgnoredContentTest(unittest.TestCase):
    def test_parens_inside_a_string_are_ignored(self) -> None:
        self.assertTrue(balanced('(display "((((")'))

    def test_escaped_quote_inside_a_string(self) -> None:
        self.assertTrue(balanced('(display "a \\" b")'))

    def test_line_comment_is_ignored(self) -> None:
        self.assertTrue(balanced("(a) ; ))))) \n(b)"))

    def test_block_comment_is_ignored_and_nests(self) -> None:
        self.assertTrue(balanced("(a) #| ) #| ) |# ) |# (b)"))

    def test_datum_comment_skips_one_form(self) -> None:
        self.assertTrue(balanced("(a #; (b) c)"))

    def test_character_literal_opening_paren(self) -> None:
        self.assertTrue(balanced("(#\\()"))

    def test_character_literal_closing_paren(self) -> None:
        self.assertTrue(balanced("(#\\))"))

    def test_named_character_literal(self) -> None:
        self.assertTrue(balanced("(a #\\space b)"))


class BrokenFormsTest(unittest.TestCase):
    def test_missing_closer(self) -> None:
        self.assertFalse(balanced("(define (f x) (+ x 1)"))

    def test_extra_closer(self) -> None:
        self.assertFalse(balanced("(a b))"))

    def test_unterminated_string(self) -> None:
        self.assertFalse(balanced('(display "abc'))

    def test_mismatched_bracket(self) -> None:
        self.assertFalse(balanced("(a]"))

    def test_unterminated_block_comment(self) -> None:
        self.assertFalse(balanced("(a) #| never closed"))


class CliTest(unittest.TestCase):
    def test_repository_scheme_is_balanced(self) -> None:
        self.assertEqual(checker.main([]), 0)

    def test_cli_reports_a_broken_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.scm"
            path.write_text("(define (f x) (+ x 1)", encoding="utf-8")
            self.assertEqual(checker.main([str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
