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

    def test_aggregate_does_not_pull_in_guix_targets(self) -> None:
        """A contributor without Guix must still be able to run `make check`."""
        pulled = sorted(aggregate(self.text) & self.guix_targets)
        self.assertEqual(pulled, [], f"`make check` requires Guix for: {pulled}")

    def test_each_python_target_runs_at_least_one_command(self) -> None:
        for name in sorted(self.python_targets):
            with self.subTest(target=name):
                self.assertIn("\t$(PYTHON)", block_for(self.text, name))



import unittest as _unittest


class ReleaseGateMakefileCoverageTests(_unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")

    def test_product_aware_release_gate_is_in_default_check(self) -> None:
        check = re.search(r"^check:\s*(.*)$", self.makefile, re.MULTILINE)
        self.assertIsNotNone(check)
        self.assertIn("check-release-gate", check.group(1))
        self.assertRegex(self.makefile, r"(?m)^check-release-gate:\s*\n\s*\$\(PYTHON\) tests/test_release_gate\.py")

    def test_release_gate_passes_explicit_product_and_defaults_to_free(self) -> None:
        self.assertRegex(self.makefile, r"(?m)^PRODUCT \?= free$")
        self.assertRegex(self.makefile, r"(?m)^release-gate:\s*\n\s*\$\(PYTHON\) scripts/release_gate\.py --product \"\$\(PRODUCT\)\"")

    def test_channel_make_target_does_not_reuse_free_lock_for_compatibility(self) -> None:
        start = self.makefile.index("check-channels:")
        end = self.makefile.find("\n[A-Za-z0-9_.-]+:", start)
        channel_rule = self.makefile[start:] if end < 0 else self.makefile[start:end]
        self.assertIn("--policy free --lock channels.lock.scm", channel_rule)
        self.assertIn("channels.compatibility.lock.scm", channel_rule)
        self.assertIn("NOT_CONFIGURED", channel_rule)

    def test_every_check_target_is_phony(self) -> None:
        phony_line = next(line for line in self.makefile.splitlines() if line.startswith(".PHONY:"))
        phony = set(phony_line.split()[1:])
        targets = re.findall(r"(?m)^([A-Za-z0-9_.-]+):", self.makefile)
        missing = {name for name in targets if name.startswith("check") and name not in phony}
        self.assertEqual(missing, set())

if __name__ == "__main__":
    unittest.main()
