# SPDX-License-Identifier: LicenseRef-Volnist
"""The Scheme module coverage checker must distinguish code from comments and strings."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_scheme_module_coverage import check  # noqa: E402

PACKAGE_MODULE = """\
(define-module (wsm packages wsm)
  #:use-module (guix packages)
  #:export (wsm-tools))
"""

SYSTEM_MODULE = """\
(define-module (wsm systems performance)
  #:use-module (guix services))
"""

EVAL_ONE = """\
(use-modules (wsm systems performance))
(display "ok")
"""

EVAL_BOTH = """\
(use-modules (wsm systems performance)
             (wsm packages wsm))
(display "ok")
"""


class CoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "wsm" / "packages").mkdir(parents=True)
        (self.root / "wsm" / "systems").mkdir(parents=True)
        (self.root / "tests" / "guix").mkdir(parents=True)
        (self.root / "wsm" / "packages" / "wsm.scm").write_text(PACKAGE_MODULE)
        (self.root / "wsm" / "systems" / "performance.scm").write_text(SYSTEM_MODULE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_eval(self, content: str) -> None:
        (self.root / "tests" / "guix" / "source-module-evaluation.scm").write_text(content)

    def test_unevaluated_module_is_reported(self) -> None:
        self.write_eval(EVAL_ONE)
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("wsm packages wsm", problems[0])

    def test_all_modules_loaded_passes(self) -> None:
        self.write_eval(EVAL_BOTH)
        self.assertEqual(check(self.root), [])

    def test_missing_evaluation_test_is_reported(self) -> None:
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("missing evaluation test", problems[0])

    def test_module_name_comes_from_the_file_not_the_path(self) -> None:
        (self.root / "wsm" / "packages" / "wsm.scm").write_text(
            PACKAGE_MODULE.replace("(wsm packages wsm)", "(wsm packages renamed)")
        )
        self.write_eval(EVAL_ONE)
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("wsm packages renamed", problems[0])

    def test_line_comment_cannot_fake_an_import(self) -> None:
        self.write_eval("; (use-modules (wsm packages wsm))\n" + EVAL_ONE)
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("wsm packages wsm", problems[0])

    def test_block_comment_cannot_fake_import_or_module(self) -> None:
        self.write_eval("#| (use-modules (wsm packages wsm)) |#\n" + EVAL_ONE)
        (self.root / "wsm" / "commented.scm").write_text(
            "#| (define-module (wsm fake module)) |#\n"
            "; (define-module (wsm another fake))\n"
        )
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("wsm packages wsm", problems[0])
        self.assertNotIn("wsm fake module", " ".join(problems))

    def test_nested_block_comments_are_ignored(self) -> None:
        self.write_eval(
            "#| outer #| nested (use-modules (wsm packages wsm)) |# end |#\n"
            + EVAL_ONE
        )
        self.assertEqual(len(check(self.root)), 1)

    def test_parentheses_and_escaped_quotes_in_strings_are_ignored(self) -> None:
        self.write_eval(
            EVAL_BOTH
            + '(display "not a form: ) (use-modules (wsm fake)) and quote: \\"")\n'
        )
        self.assertEqual(check(self.root), [])

    def test_scheme_character_literals_do_not_change_parenthesis_balance(self) -> None:
        self.write_eval('(display #\\))\n' + '(display #\\;)\n' + EVAL_BOTH)
        self.assertEqual(check(self.root), [])

    def test_duplicate_module_declarations_are_reported(self) -> None:
        (self.root / "wsm" / "packages" / "duplicate.scm").write_text(
            "(define-module (wsm packages wsm))\n"
        )
        self.write_eval(EVAL_BOTH)
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("duplicate Scheme module", problems[0])
        self.assertIn("wsm/packages/wsm.scm", problems[0])
        self.assertIn("wsm/packages/duplicate.scm", problems[0])

    def test_repository_tree_is_fully_covered(self) -> None:
        self.assertEqual(check(ROOT), [], "wsm/ modules missing from the Guix evaluation test")


if __name__ == "__main__":
    unittest.main()
