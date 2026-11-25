# SPDX-License-Identifier: GPL-3.0-or-later
"""Evidence and safety guardrails for the PCIe AER/devlink protocol."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "testing" / "PCIE-LINK-HEALTH.md"


class PcieLinkHealthProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PROTOCOL.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_aer_counter_classes_and_paths_are_separate(self) -> None:
        for path in (
            "aer_dev_correctable",
            "aer_dev_nonfatal",
            "aer_dev_fatal",
            "aer_rootport_total_err_cor",
            "aer_rootport_total_err_nonfatal",
            "aer_rootport_total_err_fatal",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.text)
        self.assertIn("correctable", self.lower)
        self.assertIn("non-fatal", self.lower)
        self.assertIn("fatal", self.lower)

    def test_missing_or_denied_data_never_becomes_zero(self) -> None:
        self.assertIn("not-collected", self.lower)
        self.assertIn("permission-denied", self.lower)
        self.assertIn("verdict unknown", self.lower)
        self.assertIn("не нуль", self.lower)

    def test_rootport_counters_are_not_endpoint_attribution(self) -> None:
        self.assertIn("root-port total counters доступні", self.lower)
        self.assertIn("вони агрегують повідомлення в pcie hierarchy", self.lower)
        self.assertIn("endpoint attribution лишається unknown", self.lower)
        self.assertIn("не можна автоматично приписати одному endpoint", self.lower)

    def test_snapshots_and_deltas_require_same_boot_and_monotonic_time(self) -> None:
        self.assertIn("snapshot cumulative counter", self.lower)
        self.assertIn("тієї самої boot session", self.lower)
        self.assertIn("монотонний час строго зростає", self.lower)
        self.assertIn("counter зменшився", self.lower)
        self.assertIn("delta unknown", self.lower)

    def test_devlink_only_allows_health_show(self) -> None:
        self.assertIn("devlink health show", self.lower)
        self.assertIn("health-reporter-get", self.lower)
        for forbidden in (
            "health-reporter-diagnose",
            "health-reporter-dump-get",
            "health-reporter-recover",
            "health-reporter-test",
            "health-reporter-set",
            "health-reporter-dump-clear",
        ):
            with self.subTest(operation=forbidden):
                self.assertIn(forbidden, self.text)
        self.assertIn("єдина дозволена команда", self.lower)

    def test_no_mutating_diagnostic_operations_are_recommended(self) -> None:
        for forbidden in (
            "setpci",
            "error injection",
            "retraining",
            "driver reload",
            "firmware update",
        ):
            with self.subTest(operation=forbidden):
                self.assertIn(forbidden, self.lower)
        self.assertIn("не змінює pcie, driver, device", self.lower)

    def test_zero_and_nonzero_counts_are_not_global_health_verdicts(self) -> None:
        self.assertIn("не healthy", self.lower)
        self.assertIn("повна справність пристрою/лінка", self.lower)
        self.assertIn("не повинен самостійно блокувати інсталяцію", self.lower)

    def test_protocol_keeps_schema_and_collector_out_of_scope(self) -> None:
        self.assertIn("validation protocol", self.lower)
        self.assertIn("власників #5/#6/#16", self.lower)
        self.assertIn("нові report fields", self.lower)


if __name__ == "__main__":
    unittest.main()
