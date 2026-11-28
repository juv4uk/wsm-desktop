# SPDX-License-Identifier: LicenseRef-Volnist
"""The Cuirass jobset must be structurally sound and honestly scoped.

Cuirass is the Guix build farm: it evaluates a jobset, builds the derivations and
serves them as substitutes. Our GitHub Actions job evaluates profiles and throws
the result away, which is why it costs 20+ minutes every time.

This repository has no Guix and no Cuirass, so the specification cannot be
registered here. What can be checked is the part that would otherwise break
silently: that the file names its inputs, that it does not build the
Compatibility profile (which carries nonfree components), and that nobody
quietly turns it into a claim that the jobset ran.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "etc" / "cuirass" / "wsm-desktop.scm"


class CuirassSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SPEC.read_text(encoding="utf-8")

    def test_the_specification_file_exists(self) -> None:
        self.assertTrue(SPEC.is_file())

    def test_it_declares_a_named_specification(self) -> None:
        self.assertRegex(self.text, r"\(specification\s*\n?\s*\(name \"[a-z0-9-]+\"\)")

    def test_it_pins_both_channels(self) -> None:
        self.assertIn("(name 'guix)", self.text)
        self.assertIn("(name 'wsm)", self.text)

    def test_it_does_not_build_the_compatibility_profile(self) -> None:
        """Free jobset must not publish nonfree derivations.

        Only code counts: a comment that *names* Nonguix while explaining why it
        is excluded is not a dependency. Stripping comments before the check is
        the same rule as "a mention in a comment is not a use".
        """
        code = "\n".join(
            line.split(";", 1)[0] for line in self.text.splitlines()
        )
        self.assertNotIn("compatibility.scm", code)
        self.assertNotIn("nonguix", code.lower())

    def test_it_states_that_it_has_not_run(self) -> None:
        self.assertIn("NOT_RUN", self.text)

    def test_it_does_not_pretend_to_prove_a_build(self) -> None:
        """The comment must keep the limit visible: a spec is not evidence."""
        self.assertIn("специфікація, а не доказ", self.text)

    def test_the_documentation_exists_and_is_linked(self) -> None:
        document = ROOT / "docs" / "CUIRASS.md"
        self.assertTrue(document.is_file(), "docs/CUIRASS.md is missing")
        text = document.read_text(encoding="utf-8")
        self.assertIn("etc/cuirass/wsm-desktop.scm", text)


if __name__ == "__main__":
    unittest.main()
