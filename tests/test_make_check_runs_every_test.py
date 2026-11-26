# SPDX-License-Identifier: LicenseRef-Volnist
"""`make check` must run every test file, not the ones someone remembered.

`CONTRIBUTING.md` tells a contributor to run `make check` before a pull
request. Nine test files were not referenced by any target — including the
compatibility verdict policy tests — so the documented command was green while
those checks never executed. CI ran them through discovery, which is exactly
why nobody noticed: the difference was invisible from the inside.

The fix is one discovery target; this test keeps it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
TESTS = ROOT / "tests"

DISCOVERY = re.compile(r"-m unittest discover -s tests -p 'test_\*\.py'")


def check_target_body() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^check:.*$", text, re.MULTILINE)
    assert match is not None, "the Makefile has no `check:` target"
    aggregate = match.group(0).split(":", 1)[1].split()
    bodies = []
    for name in aggregate:
        target = re.search(rf"^{re.escape(name)}:\n((?:\t.*\n)+)", text, re.MULTILINE)
        if target:
            bodies.append(target.group(1))
    return "".join(bodies)


class MakeCheckRunsEveryTestTests(unittest.TestCase):
    def test_check_target_runs_discovery(self) -> None:
        self.assertRegex(check_target_body(), DISCOVERY)

    def test_every_test_file_is_covered_by_discovery(self) -> None:
        """Discovery by name is the rule; a file outside the pattern is invisible."""
        outside = [
            path.name
            for path in sorted(TESTS.glob("*.py"))
            if not path.name.startswith("test_")
        ]
        self.assertEqual(outside, [], "these files would never be discovered: " + ", ".join(outside))

    def test_the_scan_is_not_empty(self) -> None:
        self.assertGreaterEqual(len(list(TESTS.glob("test_*.py"))), 50)


if __name__ == "__main__":
    unittest.main()
