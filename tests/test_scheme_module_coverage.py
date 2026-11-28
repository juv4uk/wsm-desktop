# SPDX-License-Identifier: LicenseRef-Volnist
"""A module nobody evaluates is a module nobody has checked.

The Guix evaluation test covered ``(wsm systems performance)`` only, so
``(wsm packages wsm)`` - the channel's own package module - was never loaded by
Guix at all. These tests pin the coverage rule and prove the checker is red
without it.
"""

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

    def write_eval(self, text: str) -> None:
        (self.root / "tests" / "guix" / "source-module-evaluation.scm").write_text(text)

    def test_unevaluated_module_is_reported(self) -> None:
        """The regression this file exists for: the channel module was skipped."""
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
        """A file whose define-module disagrees with its path is still tracked."""
        (self.root / "wsm" / "packages" / "wsm.scm").write_text(
            PACKAGE_MODULE.replace("(wsm packages wsm)", "(wsm packages renamed)")
        )
        self.write_eval(EVAL_ONE)
        problems = check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("wsm packages renamed", problems[0])

    def test_repository_tree_is_fully_covered(self) -> None:
        self.assertEqual(check(ROOT), [], "wsm/ modules missing from the Guix evaluation test")


if __name__ == "__main__":
    unittest.main()
