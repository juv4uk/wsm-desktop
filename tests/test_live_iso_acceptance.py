# SPDX-License-Identifier: LicenseRef-Volnist
"""Acceptance plumbing for the live image: marker in the profile, both firmwares.

The acceptance for the first bootable image is a serial marker seen in QEMU in
BIOS *and* UEFI mode. These tests check the parts that do not need QEMU: that
the profile really prints the marker, and that the harness refuses an
incomplete UEFI invocation instead of silently booting BIOS.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qemu_boot_smoke import build_qemu_command  # noqa: E402

MARKER = "WSM_LIVE_READY"


class LiveProfileMarkerTests(unittest.TestCase):
    def test_profile_prints_the_acceptance_marker(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn(MARKER, text)
        self.assertIn("/dev/console", text)

    def test_marker_service_is_registered_in_services(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("wsm-live-ready-marker", text)
        self.assertIn("(operating-system-services base-os)", text)

    def test_marker_write_cannot_break_boot(self) -> None:
        """A missing console must mean 'no marker', not 'system does not boot'."""
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("(catch #t", text)

    def test_serial_console_is_on_the_kernel_command_line(self) -> None:
        text = (ROOT / "systems" / "live.scm").read_text(encoding="utf-8")
        self.assertIn("console=ttyS0", text)


class FirmwareSelectionTests(unittest.TestCase):
    def command(self, **kwargs):
        return build_qemu_command("qemu-system-x86_64", Path("/tmp/x.iso"), Path("/tmp/x.qcow2"), 1024, 1, **kwargs)

    def test_bios_is_the_default_and_has_no_pflash(self) -> None:
        command = self.command()
        self.assertFalse(any("pflash" in part for part in command))

    def test_uefi_adds_read_only_code_and_writable_vars(self) -> None:
        command = self.command(
            firmware="uefi",
            ovmf_code=Path("/tmp/OVMF_CODE.fd"),
            ovmf_vars=Path("/tmp/OVMF_VARS.fd"),
        )
        joined = " ".join(command)
        self.assertIn("readonly=on", joined)
        self.assertIn("OVMF_CODE.fd", joined)
        self.assertIn("OVMF_VARS.fd", joined)

    def test_uefi_without_vars_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.command(firmware="uefi", ovmf_code=Path("/tmp/OVMF_CODE.fd"))


class HarnessCliTests(unittest.TestCase):
    def run_harness(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "qemu_boot_smoke.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_uefi_without_ovmf_is_refused_with_exit_2(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
            iso.write(b"not really an iso, but not empty")
            iso.flush()
            result = self.run_harness("--iso", iso.name, "--firmware", "uefi", "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--ovmf-code", result.stderr)

    def test_dry_run_reports_the_firmware(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
            iso.write(b"not really an iso, but not empty")
            iso.flush()
            result = self.run_harness("--iso", iso.name, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"firmware": "bios"', result.stdout)


if __name__ == "__main__":
    unittest.main()
