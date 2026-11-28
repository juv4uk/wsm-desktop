# SPDX-License-Identifier: LicenseRef-Volnist
"""Every package module must be named in the Guix evaluation, or it is never loaded.

The failure this prevents is quiet: add `wsm/packages/foo.scm`, forget to list it in
tests/guix/package-module-evaluation.scm, and nothing ever loads it. Syntax errors, an
unbound variable and a licence record that does not resolve all pass every other check
in this repository, because those checks read the file as text.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "wsm" / "packages"
EVALUATION = ROOT / "tests" / "guix" / "package-module-evaluation.scm"


def module_names() -> set[str]:
    """The module name for each package file, e.g. wsm/packages/wsm.scm -> (wsm packages wsm)."""
    return {
        f"(wsm packages {path.stem})"
        for path in PACKAGES.glob("*.scm")
    }


class PackageModuleEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluation = EVALUATION.read_text(encoding="utf-8")

    def test_the_evaluation_file_exists_and_is_balanced(self) -> None:
        self.assertTrue(EVALUATION.is_file())
        self.assertEqual(
            self.evaluation.count("("), self.evaluation.count(")"),
            "unbalanced parentheses: guix would refuse the file, not report a package error",
        )

    def test_every_package_module_is_loaded(self) -> None:
        loaded = set(re.findall(
            r"\(use-modules (\(wsm packages [a-z0-9-]+\))\)", self.evaluation
        ))
        missing = module_names() - loaded
        self.assertEqual(
            sorted(missing), [],
            "these package modules are never loaded by Guix: " + ", ".join(sorted(missing)),
        )

    def test_the_scan_is_not_vacuous(self) -> None:
        """If the glob found nothing, the test above would pass on an empty tree."""
        self.assertGreaterEqual(len(module_names()), 2)

    def test_each_loaded_package_is_touched_not_just_imported(self) -> None:
        """Importing a module does not force its package fields to resolve."""
        self.assertGreaterEqual(self.evaluation.count("package-license"), 2)
        self.assertGreaterEqual(self.evaluation.count("(report "), 2)

    def test_a_failure_exits_non_zero(self) -> None:
        self.assertIn("(exit 1)", self.evaluation)


if __name__ == "__main__":
    unittest.main()
