# SPDX-License-Identifier: GPL-3.0-or-later
"""Guardrails for the canonical PCIe AER/devlink evidence protocol."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "testing" / "PCIE-LINK-HEALTH.md"


class PcieLinkHealthProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PROTOCOL.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_aer_counter_classes_and_sources_are_separate(self) -> None:
        for attribute in (
            "aer_dev_correctable",
            "aer_dev_nonfatal",
            "aer_dev_fatal",
            "aer_rootport_total_err_cor",
            "aer_rootport_total_err_nonfatal",
            "aer_rootport_total_err_fatal",
        ):
            with self.subTest(attribute=attribute):
                self.assertIn(attribute, self.text)
        self.assertIn("correctable", self.lower)
        self.assertIn("non-fatal", self.lower)
        self.assertIn("fatal", self.lower)
        self.assertIn("root-port", self.lower)

    def test_missing_or_unreadable_data_is_not_zero(self) -> None:
        self.assertIn("not-collected", self.lower)
        self.assertIn("unknown", self.lower)
        self.assertIn("не підміняти його нулем", self.lower)
        self.assertIn("permission denied", self.lower)

    def test_rootport_totals_are_not_attributed_to_one_endpoint(self) -> None:
        self.assertIn("root port totals агрегують", self.lower)
        self.assertIn("не приписувати їх автоматично downstream endpoint", self.lower)
        self.assertIn("endpoint-проблема може бути зафіксована", self.lower)
        self.assertIn("link partner або root port", self.lower)

    def test_delta_requires_same_boot_and_monotonic_order(self) -> None:
        self.assertIn("та сама boot session", self.lower)
        self.assertIn("монотонний порядок часу", self.lower)
        self.assertIn("лічильник зменшився", self.lower)
        self.assertIn("delta є unknown", self.lower)
        self.assertIn("зміни джерела", self.lower)

    def test_only_devlink_health_show_is_allowed_automatically(self) -> None:
        self.assertIn("devlink health show", self.lower)
        self.assertIn("health-reporter-get", self.lower)
        self.assertIn("не запускати автоматично", self.lower)
        for forbidden in (
            "devlink health recover",
            "devlink health test",
            "devlink health diagnose",
            "devlink health dump show",
            "devlink health dump clear",
            "devlink health set",
        ):
            with self.subTest(operation=forbidden):
                self.assertIn(forbidden, self.lower)

    def test_no_mutating_diagnostic_operations_are_recommended(self) -> None:
        for forbidden in (
            "error injection",
            "stress/throughput tests",
            "link retraining",
            "device reset",
            "driver reload",
            "firmware update/flash",
            "recovery процедури",
        ):
            with self.subTest(operation=forbidden):
                self.assertIn(forbidden, self.lower)

    def test_zero_and_nonzero_values_are_not_global_health_verdicts(self) -> None:
        self.assertIn("нульовий не доводить", self.lower)
        self.assertIn("нульове значення", self.lower)
        self.assertIn("не доводить, що link або пристрій здоровий", self.lower)
        self.assertIn("не повинні самостійно встановлювати hard-stop", self.lower)

    def test_device_attribution_requires_explicit_topology(self) -> None:
        self.assertIn("явні topology relationships", self.lower)
        self.assertIn("report-local device id", self.lower)
        self.assertIn("абсолютний sysfs path не є стабільним public identifier", self.lower)
        self.assertIn("не поширюється на інші пристрої", self.lower)


if __name__ == "__main__":
    unittest.main()
