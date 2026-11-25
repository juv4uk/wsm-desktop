# SPDX-License-Identifier: GPL-3.0-or-later
"""Repository documentation checks."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
