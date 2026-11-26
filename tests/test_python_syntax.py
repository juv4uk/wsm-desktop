# SPDX-License-Identifier: LicenseRef-Volnist
"""Fail fast when a tracked Python file does not parse.

Four pull requests in one day arrived with a file that had been written only
partly: a module truncated mid-call, a test file missing an import, a CI script
whose string concatenation lost its operator. None of those are logic errors,
and none were caught by review, because the diff looked plausible.

Parsing every tracked file costs milliseconds and turns that whole class of
mistake into a red check instead of a broken release tool.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {".git", "__pycache__", "build"}


def python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not SKIP_DIRECTORIES.intersection(path.parts)
    )


class PythonSyntaxTests(unittest.TestCase):
    def test_every_tracked_python_file_parses(self) -> None:
        files = python_files()
        self.assertGreater(len(files), 10, "suspiciously few Python files found")
        broken: list[str] = []
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                broken.append(
                    f"{path.relative_to(ROOT)}:{error.lineno}: {error.msg}"
                )
        self.assertEqual(broken, [], "files that do not parse:\n" + "\n".join(broken))

    def test_truncated_file_is_detected(self) -> None:
        """The guard must actually fail on the shape of mistake it exists for."""
        with self.assertRaises(SyntaxError):
            ast.parse("def prepare(\n    _require(\n        True,\n", filename="truncated.py")


if __name__ == "__main__":
    unittest.main()
