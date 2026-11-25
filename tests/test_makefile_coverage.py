# SPDX-License-Identifier: LicenseRef-Volnist
"""Every check-* target must actually run from `make check`.

Three of my earlier targets were added to the Makefile but never to the
aggregate line, so `make check` silently skipped them. That is the same class of
mistake as a CI that reports queued: the check exists, and nobody runs it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


def targets(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^(check-[a-z0-9-]+):", text, re.MULTILINE)
    }


def aggregate(text: str) -> set[str]:
    for line in text.splitlines():
        if line.startswith("check:"):
            return set(line.split(":")[1].split())
    raise AssertionError("no aggregate check target")


def phony_targets(text: str) -> set[str]:
    result: set[str] = set()
    for line in text.splitlines():
        if line.startswith(".PHONY:"):
            result.update(line.split(":", 1)[1].split())
    return result


def block_for(text: str, name: str) -> str:
    return text.split(f"{name}:", 1)[1].split("\n\n", 1)[0]


class MakefileCoverageTests(unittest.TestCase):
    """Targets that need Guix are exempt: `make check` must work without it."""

    def setUp(self) -> None:
        self.text = MAKEFILE.read_text(encoding="utf-8")
        self.all_targets = targets(self.text)
        self.guix_targets = {
            name for name in self.all_targets
            if "$(GUIX)" in block_for(self.text, name)
        }
        self.python_targets = self.all_targets - self.guix_targets

    def test_every_python_target_is_in_the_aggregate(self) -> None:
        missing = sorted(self.python_targets - aggregate(self.text))
        self.assertEqual(missing, [], f"not run by `make check`: {missing}")

    def test_aggregate_does_not_reference_missing_targets(self) -> None:
        unknown = sorted(aggregate(self.text) - self.all_targets)
        self.assertEqual(unknown, [], f"aggregate mentions non-existent targets: {unknown}")

    def test_every_check_target_is_phony(self) -> None:
        missing = sorted(self.all_targets - phony_targets(self.text))
        self.assertEqual(missing, [], f"check targets must be .PHONY: {missing}")

    def test_aggregate_does_not_pull_in_guix_targets(self) -> None:
        """A contributor without Guix must still be able to run `make check`."""
        pulled = sorted(aggregate(self.text) & self.guix_targets)
        self.assertEqual(pulled, [], f"`make check` requires Guix for: {pulled}")

    def test_each_python_target_runs_at_least_one_command(self) -> None:
        for name in sorted(self.python_targets):
            with self.subTest(target=name):
                self.assertIn("\t$(PYTHON)", block_for(self.text, name))


if __name__ == "__main__":
    unittest.main()
