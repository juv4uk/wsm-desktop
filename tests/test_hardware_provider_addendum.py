# SPDX-License-Identifier: GPL-3.0-or-later
"""Guardrails for optional GPU telemetry and hwmon provider semantics."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "hardware" / "UPSTREAM-TOOLING-ADDENDUM-2026-11-25.md"


class OptionalHardwareProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = AUDIT.read_text(encoding="utf-8")
        cls.lower = cls.audit.casefold()

    def test_optional_providers_are_not_required_for_inventory(self) -> None:
        self.assertIn("не повинен бути необхідним для успішного inventory", self.lower)
        self.assertIn("not-collected/unknown", self.audit)
        self.assertIn("не блокують installer", self.lower)

    def test_nvml_uses_pci_identity_and_keeps_gpu_initialization_side_effect(self) -> None:
        self.assertIn("NVML_ERROR_NO_PERMISSION", self.audit)
        self.assertIn("nvmlDeviceGetHandleByPciBusId_v2", self.audit)
        self.assertIn("не гарантується між перезавантаженнями", self.lower)
        self.assertIn("можуть ініціалізувати цільовий gpu", self.lower)
        self.assertIn("не є буквально пасивним filesystem reader", self.lower)
        self.assertIn("opt-in diagnostics/support mode", self.lower)
        self.assertIn("GeForce/RTX", self.audit)
        self.assertIn("board serial", self.lower)

    def test_displayid_parser_candidate_is_security_gated(self) -> None:
        self.assertIn("CVE-2026-112271", self.audit)
        self.assertIn("CVE-2026-112272", self.audit)
        self.assertIn("не додавати libdisplay-info 0.4.0 до стандартного live image", self.lower)
        self.assertIn("до підтвердженого upstream-виправлення", self.lower)

    def test_intel_xpu_smi_is_limited_to_documented_device_families(self) -> None:
        self.assertIn("Arc Pro Series", self.audit)
        self.assertIn("не дає підстав автоматично заявляти підтримку всіх intel igpu/consumer arc", self.lower)
        self.assertIn("xpu-smi discovery --device <BDF> -j", self.audit)
        self.assertIn("SOC UUID", self.audit)
        self.assertIn("firmware update", self.lower)
        self.assertIn("не використовувати безмежний", self.lower)

    def test_hwmon_channel_numbers_are_not_physical_sensor_names(self) -> None:
        self.assertIn("RO, WO і RW", self.audit)
        self.assertIn("temp*_input", self.audit)
        self.assertIn("fan*_input", self.audit)
        self.assertIn("номер каналу сам по собі не означає", self.lower)
        self.assertIn("libsensors", self.audit)

    def test_preflight_excludes_sensor_and_gpu_mutations(self) -> None:
        for token in (
            "reset_history",
            "update_interval",
            "clock offsets",
            "firmware update",
            "reset",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.lower)

    def test_provider_reports_keep_identifiers_out_of_sanitized_output(self) -> None:
        for token in ("uuid", "serial", "hostname", "part number"):
            with self.subTest(token=token):
                self.assertIn(token, self.lower)
        self.assertIn("allowlist", self.lower)


if __name__ == "__main__":
    unittest.main()
