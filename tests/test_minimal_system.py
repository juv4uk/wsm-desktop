# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for the VM-facing minimal Guix System example."""

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

        self.assertIn("defaults to direct-kernel boot", readme)
        self.assertIn("does **not** exercise the bootloader", readme)
        self.assertIn("guix system vm --full-boot", readme)
        self.assertIn("guix system image --image-type=qcow2", readme)
        self.assertNotIn("builds an MBR disk image", readme)

    def test_readme_explains_the_uefi_override(self) -> None:
        readme = (ROOT / "systems" / "README.md").read_text(encoding="utf-8")

        self.assertIn("grub-efi-bootloader", readme)
        self.assertIn("/boot/efi", readme)
        self.assertIn("GPT", readme)


if __name__ == "__main__":
    unittest.main()
