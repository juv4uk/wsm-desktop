# SPDX-License-Identifier: LicenseRef-Volnist
"""Two builds failed on a missing import. This catches the next one earlier."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_scheme_imports import check, imported_modules  # noqa: E402

GOOD = """
(define-module (wsm test)
  #:use-module (guix utils)
  #:use-module (srfi srfi-1))
(version-major+minor "3.12")
(any even? '(1 2))
"""

MISSING_UTILS = """
(define-module (wsm test)
  #:use-module (guix packages))
(version-major+minor "3.12")
"""

MISSING_SRFI = """
(define-module (wsm test))
(any even? '(1 2))
"""

COMMENT_ONLY = """
(define-module (wsm test))
;; version-major+minor is not used here, only mentioned
(display "hello")
"""


def write(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".scm", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return Path(handle.name)


class ImportTests(unittest.TestCase):
    def test_imported_modules_are_parsed(self) -> None:
        modules = imported_modules(GOOD)
        self.assertIn("guix utils", modules)
        self.assertIn("srfi srfi-1", modules)

    def test_missing_guix_utils_is_reported(self) -> None:
        problems = check(write(MISSING_UTILS))
        self.assertTrue(problems)
        self.assertIn("version-major+minor", problems[0])
        self.assertIn("guix utils", problems[0])

    def test_missing_srfi_is_reported(self) -> None:
        problems = check(write(MISSING_SRFI))
        self.assertTrue(problems)
        self.assertIn("any", problems[0])

    def test_complete_imports_pass(self) -> None:
        self.assertEqual(check(write(GOOD)), [])

    def test_a_mention_in_a_comment_is_not_a_use(self) -> None:
        """Documentation that names a helper must not fail the check."""
        self.assertEqual(check(write(COMMENT_ONLY)), [])

    def test_a_missing_root_is_reported_not_skipped(self) -> None:
        """Scanning nothing must not look like scanning everything."""
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_scheme_imports.py"),
             str(ROOT / "systems-does-not-exist")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("root does not exist", completed.stderr)

    def test_the_repository_scan_is_not_empty(self) -> None:
        """If the default roots stopped matching, the pass would be vacuous."""
        scanned = [
            path
            for root in (ROOT / "systems", ROOT / "wsm")
            for path in root.rglob("*.scm")
        ]
        self.assertGreaterEqual(len(scanned), 10, [str(path) for path in scanned])

    def test_the_repository_itself_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_scheme_imports.py"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
