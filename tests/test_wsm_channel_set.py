# SPDX-License-Identifier: LicenseRef-Volnist
"""Structural guard for the moving WSM development channel set."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_scheme_module_coverage import mask_scheme_non_code  # noqa: E402

CHANNEL_FILE = ROOT / "channels" / "wsm.scm"
README_FILE = ROOT / "channels" / "README.md"


def channel_forms(source: str) -> list[str]:
    """Return balanced channel forms after masking Scheme comments and strings."""
    code = mask_scheme_non_code(source)
    forms: list[str] = []
    marker = re.compile(r"\(channel(?=\s|\))")
    for match in marker.finditer(code):
        depth = 0
        for index in range(match.start(), len(code)):
            if code[index] == "(":
                depth += 1
            elif code[index] == ")":
                depth -= 1
                if depth == 0:
                    forms.append(code[match.start():index + 1])
                    break
    return forms


class WsmChannelSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CHANNEL_FILE.read_text(encoding="utf-8")
        self.code = mask_scheme_non_code(self.source)

    def test_inherits_the_official_guix_channel_instead_of_redeclaring_it(self) -> None:
        self.assertIn("(use-modules (guix channels))", self.code)
        self.assertIn("%default-channels", self.code)
        self.assertNotIn("(name 'guix)", self.code)
        self.assertNotRegex(self.code, r"\(branch\s+#f\)")

    def test_declares_exactly_one_wsm_channel_on_main(self) -> None:
        forms = channel_forms(self.source)
        self.assertEqual(len(forms), 1, f"expected one explicit WSM channel, got {forms}")
        self.assertIn("(name 'wsm)", forms[0])
        self.assertRegex(self.source, r'\(url\s+"https://github\.com/juv4uk/wsm-desktop"\)')
        self.assertRegex(self.source, r'\(branch\s+"main"\)')
        self.assertIn("(cons*", self.code)

    def test_does_not_claim_wsm_authentication_before_owner_bootstrap(self) -> None:
        self.assertNotIn("(introduction", self.code)
        self.assertIn(".guix-authorizations", self.source)
        self.assertIn("keyring", self.source)
        self.assertIn("not evidence that the WSM channel is authenticated", self.source)

    def test_documentation_keeps_diagnostic_authentication_bypass_out_of_release(self) -> None:
        docs = README_FILE.read_text(encoding="utf-8")
        self.assertIn("--disable-authentication", docs)
        self.assertIn("Не використовуйте", docs)
        self.assertIn("WSM_CHANNEL_AUTHENTICATION=NOT_TESTED", docs)
        self.assertIn("guix git authenticate", docs)


if __name__ == "__main__":
    unittest.main()
