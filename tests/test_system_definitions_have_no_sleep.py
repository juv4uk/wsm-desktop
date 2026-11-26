# SPDX-License-Identifier: LicenseRef-Volnist
"""Shipped system definitions must not buy readiness with a sleep.

The Omarchy regression (#20059) is a DRM hand-off race: the compositor starts
before the kernel driver has taken over from simpledrm. The fix that agents
reach for — a fixed ``sleep``, or a global ``udevadm settle`` before the display
manager — makes the race rarer instead of closing it, and turns a fast machine
into a slow one.

We cannot prove on this hardware that DRM is ready before SDDM. What we can do
is forbid the known bad fix from entering the shipped system definitions, so it
is caught at review time rather than six months later as an intermittent
black screen.

Scope is deliberate: ``systems/*.scm`` are the definitions that ship. Test
harnesses under ``scripts/`` wait for their own guests and are out of scope.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ROOT / "systems"

SLEEP = re.compile(r"\(sleep\b|\bsleep\s+\d|\bsleep\s+\$\{")
UDEV_SETTLE = re.compile(r"udev-settle|udevadm[^\n]*\bsettle\b")


def offences(text: str) -> list[str]:
    """Return the offending lines of one system definition."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(";"):
            continue
        if SLEEP.search(line):
            found.append(f"line {number}: fixed sleep used as readiness: {stripped}")
        if UDEV_SETTLE.search(line):
            found.append(f"line {number}: global udev settle used as readiness: {stripped}")
    return found


class SystemDefinitionReadinessTests(unittest.TestCase):
    def test_no_shipped_definition_waits_with_sleep(self) -> None:
        problems: list[str] = []
        for path in sorted(SYSTEMS.glob("*.scm")):
            problems.extend(f"{path.name}: {item}" for item in offences(path.read_text(encoding="utf-8")))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_scan_is_not_empty(self) -> None:
        """If the glob stopped matching, the test above would pass vacuously."""
        self.assertGreaterEqual(len(list(SYSTEMS.glob("*.scm"))), 3)

    def test_the_rule_catches_the_fix_it_was_written_for(self) -> None:
        sample = """
(define wait
  ;; a comment about sleep is not a use
  (sleep 2))
"""
        self.assertTrue(offences(sample))

    def test_the_rule_catches_a_global_udev_settle(self) -> None:
        self.assertTrue(offences('(system* "udevadm" "settle")'))

    def test_a_comment_is_not_an_offence(self) -> None:
        self.assertEqual(offences("; (sleep 2) — never do this\n"), [])


if __name__ == "__main__":
    unittest.main()
