# SPDX-License-Identifier: GPL-3.0-or-later
"""Policy guardrails for a future sanitized UEFI pre-boot provider."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "hardware" / "UEFI-PREBOOT-PROBE-AUDIT.md"


class UefiPrebootProbePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = AUDIT.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_existing_wsm_os_code_is_not_declared_safe_to_copy(self) -> None:
        self.assertIn("не переносити", self.lower)
        self.assertIn("власну текстову ліцензію", self.lower)
        self.assertIn("вольність", self.lower)
        self.assertIn("12b36c0d17e13b8cd2bb7999f82ac2511d30ea8e", self.text)
        self.assertIn("477dad9c9dd9731a94707168f72e2271b9919fd5", self.text)
        self.assertIn("ab194e332ddecf06ff1b28b8cb88f1c30de25ba9", self.text)

    def test_msr_write_and_microcode_probe_are_excluded(self) -> None:
        self.assertIn("wrmsr", self.lower)
        self.assertIn("ia32_bios_sign_id", self.lower)
        self.assertIn("strict read-only", self.lower)
        self.assertIn("це не завантаження нового microcode", self.lower)

    def test_raw_addresses_and_unique_inventory_identifiers_are_excluded(self) -> None:
        for value in (
            "framebufferbase",
            "physicalstart",
            "smbios serial",
            "uuid",
            "asset tags",
            "raw tables",
            "фізичні адреси",
        ):
            with self.subTest(value=value):
                self.assertIn(value.casefold(), self.lower)

    def test_gop_is_not_a_linux_drm_or_kms_functional_pass(self) -> None:
        self.assertIn("gop не є linux display test", self.lower)
        self.assertIn("drm/kms", self.lower)
        self.assertIn("не доводить linux drm/kms binding", self.lower)
        self.assertIn("setmode", self.lower)

    def test_memory_map_is_a_preboot_snapshot_not_linux_runtime_memory(self) -> None:
        self.assertIn("getmemorymap()", self.lower)
        self.assertIn("до exitbootservices()", self.lower)
        self.assertIn("mapkey", self.lower)
        self.assertIn("linux memavailable", self.lower)

    def test_qemu_ovmf_provenance_is_not_physical_uefi(self) -> None:
        self.assertIn("qemu-ovmf", self.lower)
        self.assertIn("physical-uefi", self.lower)
        self.assertIn("128 mib", self.lower)
        self.assertIn("115200", self.lower)
        self.assertIn("30 секунд", self.lower)

    def test_production_schema_is_not_modified_silently(self) -> None:
        self.assertIn("schema v1.0.0", self.lower)
        self.assertIn("окремий pre-boot evidence envelope", self.lower)
        self.assertIn("#5", self.lower)


if __name__ == "__main__":
    unittest.main()
