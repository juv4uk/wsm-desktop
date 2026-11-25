# SPDX-License-Identifier: GPL-3.0-or-later
"""Privacy/evidence guardrails for the display and network validation protocols."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_PROTOCOL = ROOT / "docs" / "testing" / "DISPLAY-COMPATIBILITY.md"
NETWORK_PROTOCOL = ROOT / "docs" / "testing" / "NETWORK-READINESS.md"


class ValidationProtocolPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.display = DISPLAY_PROTOCOL.read_text(encoding="utf-8")
        cls.network = NETWORK_PROTOCOL.read_text(encoding="utf-8")

    def test_display_protocol_never_exports_the_raw_kernel_command_line(self) -> None:
        self.assertIn("Не зберігати та не експортувати `/proc/cmdline` цілком", self.display)
        self.assertNotIn("cat /proc/cmdline", self.display)
        self.assertIn("allowlisted parser", self.display)

    def test_display_identity_is_opaque_by_default(self) -> None:
        self.assertIn("opaque report-local display ID із санітизованими capability facts", self.display)
        self.assertIn("manufacturer/model/name strings з EDID за замовчуванням", self.display)
        self.assertIn("явної згоди", self.display)

    def test_network_not_collected_is_coverage_not_a_verdict(self) -> None:
        self.assertIn("`not-collected` — це **маркер покриття collector-а**", self.network)
        self.assertIn("Похідний verdict для такого рівня має бути `unknown`", self.network)
        self.assertIn("`not-tested`", self.network)
        self.assertIn("`not-detected`", self.network)
        self.assertIn("не задовольняє installation-/first-boot-critical evidence gate", self.network)

    def test_network_endpoint_consent_discloses_source_ip_visibility(self) -> None:
        self.assertIn("source/egress-IP visibility", self.network)
        self.assertIn("NAT/proxy egress address", self.network)
        self.assertIn("resolver або endpoint може логувати ці дані", self.network)
        self.assertIn("source/egress IP не зберігається в публічному profile record", self.network)

    def test_displayid_parser_cves_are_treated_as_untrusted_input_risk(self) -> None:
        audit = (ROOT / "docs" / "hardware" / "UPSTREAM-TOOLING-ADDENDUM-2026-11-25.md").read_text(encoding="utf-8")
        self.assertIn("CVE-2026-112271", audit)
        self.assertIn("CVE-2026-112272", audit)
        self.assertIn("through 0.4.0", audit)
        self.assertIn("RHEL-релізи не уражені", audit)
        self.assertIn("не запускається з підвищеними привілеями", audit)
        self.assertIn("crafted EDID слід вважати untrusted input", audit)


if __name__ == "__main__":
    unittest.main()
