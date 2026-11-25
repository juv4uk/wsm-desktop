# SPDX-License-Identifier: LicenseRef-Volnist
"""Evidence and safety guardrails for the PCIe AER/devlink protocol."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "testing" / "PCIE-LINK-HEALTH.md"


class PcieLinkHealthProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PROTOCOL.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_all_device_and_rootport_counter_classes_are_separate(self) -> None:
        for name in (
            "aer_dev_correctable",
            "aer_dev_nonfatal",
            "aer_dev_fatal",
            "aer_rootport_total_err_cor",
            "aer_rootport_total_err_nonfatal",
            "aer_rootport_total_err_fatal",
        ):
            with self.subTest(attribute=name):
                self.assertIn(name, self.text)
        self.assertIn("correctable", self.lower)
        self.assertIn("non-fatal", self.lower)
        self.assertIn("fatal", self.lower)

    def test_missing_and_unreadable_attributes_remain_unknown(self) -> None:
        self.assertIn("not-collected", self.lower)
        self.assertIn("permission denied", self.lower)
        self.assertIn("не підміняти його нулем", self.lower)

    def test_rootport_aggregates_are_not_assigned_to_an_endpoint(self) -> None:
        self.assertIn("root port totals агрегують повідомлення", self.lower)
        self.assertIn("не приписувати їх автоматично downstream endpoint", self.lower)
        self.assertIn("relationship відсутній або unknown", self.lower)

    def test_delta_requires_same_boot_session_and_monotonic_time(self) -> None:
        self.assertIn("та сама boot session", self.lower)
        self.assertIn("монотонний порядок часу", self.lower)
        self.assertIn("лічильник зменшився", self.lower)
        self.assertIn("delta є", self.lower)

    def test_automatic_devlink_access_is_limited_to_show(self) -> None:
        self.assertIn("devlink health show", self.lower)
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

    def test_protocol_excludes_mutating_pcie_diagnostics(self) -> None:
        for forbidden in (
            "error injection",
            "link retraining",
            "device reset",
            "driver reload",
            "firmware update",
        ):
            with self.subTest(operation=forbidden):
                self.assertIn(forbidden, self.lower)

    def test_counters_are_not_global_health_or_installation_verdicts(self) -> None:
        self.assertIn("нульовий не доводить", self.lower)
        self.assertIn("не повинні самостійно встановлювати hard-stop сумісності", self.lower)

    def test_protocol_is_documentation_not_a_collector_or_schema_change(self) -> None:
        self.assertIn("протокол read-only", self.lower)
        self.assertIn("report-local device id", self.lower)


if __name__ == "__main__":
    unittest.main()
