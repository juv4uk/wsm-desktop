# SPDX-License-Identifier: GPL-3.0-or-later
"""Регресійні перевірки мінімального Guix System VM-профілю."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MinimalSystemTests(unittest.TestCase):
    def test_config_selects_bios_grub_for_full_boot_vm_profile(self) -> None:
        raw = (ROOT / "systems" / "minimal.scm").read_text(encoding="utf-8")
        config = "\n".join(
            line for line in raw.splitlines() if not line.lstrip().startswith(";;")
        )

        self.assertIn("(bootloader grub-bootloader)", config)
        self.assertIn('(targets \'("/dev/vda"))', config)
        self.assertNotIn("grub-efi-bootloader", config)
        self.assertNotIn("/boot/efi", config)

    def test_documentation_distinguishes_guix_vm_boot_paths(self) -> None:
        readme = (ROOT / "systems" / "README.md").read_text(encoding="utf-8")

        self.assertIn("завантаження безпосередньо ядра", readme)
        self.assertIn("не перевіряє bootloader", readme)
        self.assertIn("guix system vm --full-boot", readme)
        self.assertIn("guix system image --image-type=qcow2", readme)

    def test_readme_records_the_observed_direct_kernel_boot(self) -> None:
        readme = (ROOT / "systems" / "README.md").read_text(encoding="utf-8")

        self.assertIn("guix system build systems/minimal.scm", readme)
        self.assertIn("exit=0", readme)
        self.assertIn("wsm-desktop login:", readme)
        self.assertIn("QEMU", readme)
        self.assertIn("TCG", readme)

    def test_readme_does_not_claim_grub_full_boot_is_verified(self) -> None:
        readme = (ROOT / "systems" / "README.md").read_text(encoding="utf-8")

        self.assertIn("повний boot через GRUB не підтверджений", readme)
        self.assertIn("600 секунд", readme)
        self.assertIn("не автентифікований lock-файл", readme)

    def test_readme_explains_the_uefi_override(self) -> None:
        readme = (ROOT / "systems" / "README.md").read_text(encoding="utf-8")

        self.assertIn("grub-efi-bootloader", readme)
        self.assertIn("/boot/efi", readme)
        self.assertIn("GPT", readme)


if __name__ == "__main__":
    unittest.main()
