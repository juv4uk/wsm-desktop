# SPDX-License-Identifier: LicenseRef-Volnist
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
        for term in ("serial numbers", "mac addresses", "сирі edid blobs"):
            with self.subTest(term=term):
                self.assertIn(term, self.lower)
        self.assertIn("не змінює sysfs", self.lower)


    def test_not_collected_maps_to_unknown_not_not_tested_or_not_detected(self) -> None:
        self.assertIn("`not-collected`", self.text)
        self.assertIn("verdict має бути `unknown`", self.lower)
        self.assertIn("це не `not-tested`", self.lower)
        self.assertIn("і не `not-detected`", self.lower)
        self.assertIn("не може задовольняти critical evidence gate", self.lower)

    def test_not_detected_critical_function_requires_confirmed_fallback(self) -> None:
        self.assertIn("якщо вона critical і fallback не підтверджено", self.lower)
        self.assertIn("не дозволяти confirmable plan", self.lower)




EVIDENCE_STATES = {
    "supported-tested",
    "driver-bound-not-tested",
    "candidate-only",
    "known-problem",
    "not-detected",
    "not-tested",
    "not-collected",
    "unknown",
}


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


class DecisionLevelTests(unittest.TestCase):
    """Stop levels and the coarse three-tier words must stay derived."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = POLICY.read_text(encoding="utf-8")

    def test_four_decision_levels_are_named(self) -> None:
        block = section(self.text, "## 4.1")
        for level in ("hard-stop", "soft-stop", "warn-and-continue", "continue"):
            with self.subTest(level=level):
                self.assertIn(f"`{level}`", block)

    def test_hard_stop_does_not_claim_incompatibility(self) -> None:
        block = section(self.text, "## 4.1")
        self.assertIn("не означає «залізо несумісне»", block)
        self.assertIn("заборонене", block)

    def test_warning_cannot_escalate_silently(self) -> None:
        block = section(self.text, "## 4.1")
        self.assertIn("не може непомітно стати `hard-stop`", block)

    def test_certified_has_a_bounded_validity(self) -> None:
        """`certified` must name what invalidates it, not just what earns it."""
        block = section(self.text, "## 4.2")
        self.assertIn("Строк дії `certified`", block)
        for cause in ("profile.scm", "реліз ядра", "firmware"):
            with self.subTest(cause=cause):
                self.assertIn(cause, block)
        self.assertIn("анулюється", block)

    def test_hard_stop_covers_a_report_gap(self) -> None:
        """`not-collected` blocks too, but must not be worded as a machine verdict."""
        block = section(self.text, "## 4.1")
        hard_stop = next(
            line for line in block.splitlines() if line.startswith("| `hard-stop`")
        )
        self.assertIn("`not-collected`", hard_stop)
        self.assertIn("прогалина у звіті", block)
        self.assertIn("а не вирок машині", block)

    def test_coarse_tiers_map_only_to_known_evidence_states(self) -> None:
        """A three-word UI vocabulary may not invent a state we do not have."""
        # Only the mapping table: the validity table further down also starts
        # its rows with a backticked token.
        block = section(self.text, "## 4.2").split("### Строк дії")[0]
        rows = [line for line in block.splitlines() if line.startswith("| `")]
        self.assertGreaterEqual(len(rows), 3, rows)
        for line in rows:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            tier = cells[0].strip("`")
            self.assertIn(tier, {"certified", "known", "unknown"}, line)
            for state in EVIDENCE_STATES:
                if f"`{state}`" in cells[1]:
                    break
            else:
                self.fail(f"{tier}: maps to no known evidence state: {cells[1]}")

    def test_coarse_tiers_are_declared_derived(self) -> None:
        block = section(self.text, "## 4.2")
        self.assertIn("згортання", block)
        self.assertIn("ніколи не приймаються за трирівневою мовою", block)


if __name__ == "__main__":
    unittest.main()
