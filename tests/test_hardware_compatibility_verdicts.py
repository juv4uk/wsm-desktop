# SPDX-License-Identifier: GPL-3.0-or-later
"""Guardrails for the proposed hardware compatibility verdict policy."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "HARDWARE-COMPATIBILITY-VERDICTS.md"


class HardwareCompatibilityVerdictPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = POLICY.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_evidence_states_are_explicit_and_separate(self) -> None:
        for state in (
            "supported-tested",
            "driver-bound-not-tested",
            "candidate-only",
            "known-problem",
            "not-detected",
            "not-tested",
            "unknown",
        ):
            with self.subTest(state=state):
                self.assertIn(f"`{state}`", self.text)

    def test_impact_axis_is_independent(self) -> None:
        for impact in (
            "installation-critical",
            "first-boot-critical",
            "important-after-install",
            "optional",
        ):
            with self.subTest(impact=impact):
                self.assertIn(f"`{impact}`", self.text)
        self.assertIn("три незалежні виміри", self.lower)

    def test_unknown_is_an_evidence_gate_not_incompatibility(self) -> None:
        self.assertIn("evidence gate не є твердженням про несумісність", self.lower)
        self.assertIn("зупинити підтвердження плану", self.lower)
        self.assertIn("не блокувати", self.lower)

    def test_firmware_stages_are_not_collapsed(self) -> None:
        stages = (
            "firmware package declared",
            "package included",
            "blob present",
            "firmware request observed",
            "explicit request failure",
            "device driver bound",
            "device/function initialized",
        )
        positions = [self.lower.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_missing_logs_are_not_success_evidence(self) -> None:
        self.assertIn("відсутність помилки в журналі не є доказом", self.lower)
        self.assertIn("відсутній лог", self.lower)

    def test_positive_test_is_scoped_to_exact_function(self) -> None:
        self.assertIn("конкретної функції", self.lower)
        self.assertIn("ядро", self.lower)
        self.assertIn("метод", self.lower)
        self.assertIn("час", self.lower)

    def test_usb_composite_interfaces_are_evaluated_separately(self) -> None:
        self.assertIn("`*:1.n`", self.lower)
        self.assertIn("sibling-інтерфейсів", self.lower)

    def test_privacy_and_read_only_boundaries_are_documented(self) -> None:
        for term in ("serial numbers", "mac addresses", "raw edid blobs"):
            with self.subTest(term=term):
                self.assertIn(term, self.lower)
        self.assertIn("не змінює sysfs", self.lower)


if __name__ == "__main__":
    unittest.main()
