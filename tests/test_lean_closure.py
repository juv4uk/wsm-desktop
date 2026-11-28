# SPDX-License-Identifier: LicenseRef-Volnist
"""The channel package must not drag a full interpreter into every closure.

The published `wsm-tools` pack was 399 MB of store, of which ~226 MB was three
separate Python builds. The package is a sysfs reader and a planner; none of
that needs a development interpreter with its test suite.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "wsm" / "packages" / "wsm.scm"


class LeanClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PACKAGE.read_text(encoding="utf-8")

    def test_the_package_uses_the_minimal_interpreter(self) -> None:
        self.assertIn("python-minimal", self.text)

    def test_the_full_interpreter_is_not_propagated(self) -> None:
        """`python` in propagated-inputs is what multiplied the closure."""
        match = re.search(r"\(propagated-inputs\s*\(list([^)]*)\)", self.text)
        self.assertIsNotNone(match, "package has no propagated-inputs")
        inputs = match.group(1).split()
        self.assertNotIn("python", inputs, f"full interpreter propagated: {inputs}")

    def test_the_import_for_the_minimal_interpreter_is_present(self) -> None:
        """An unimported binding fails only when Guix evaluates the module."""
        if "python-minimal" in self.text:
            self.assertIn("(gnu packages python-build)", self.text)

    def test_json_validation_is_still_available(self) -> None:
        """The saving must not come from dropping a real dependency."""
        self.assertIn("python-jsonschema", self.text)

    def test_nothing_is_pulled_in_that_the_code_never_imports(self) -> None:
        for unused in ("python-lxml", "python-pygments", "python-setuptools"):
            self.assertNotIn(unused, self.text)


if __name__ == "__main__":
    unittest.main()
