# SPDX-License-Identifier: LicenseRef-Volnist
"""Acceptance plumbing for the live image: marker in the profile, both firmwares.

The acceptance for the first bootable image is a serial marker seen in QEMU in
BIOS *and* UEFI mode. These tests check the parts that do not need QEMU: that
the profile really prints the marker, and that the harness refuses an
incomplete UEFI invocation instead of silently booting BIOS.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import qemu_boot_smoke  # noqa: E402
from qemu_boot_smoke import (  # noqa: E402
    build_qemu_command,
    copy_ovmf_vars_template,
)

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

    def test_uefi_without_both_ovmf_files_is_refused_with_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code.write_bytes(b"code image")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code), "--dry-run",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--ovmf-vars", result.stderr)

    def test_vars_template_is_copied_without_modifying_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "OVMF_VARS.fd"
            destination = root / "private" / "OVMF_VARS.fd"
            template.write_bytes(b"separate vars template bytes")
            destination.parent.mkdir()
            copied = copy_ovmf_vars_template(template, destination)
            self.assertEqual(copied, destination)
            self.assertEqual(copied.read_bytes(), b"separate vars template bytes")
            self.assertEqual(template.read_bytes(), b"separate vars template bytes")

    def test_empty_vars_template_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "OVMF_VARS.fd"
            destination = root / "private" / "OVMF_VARS.fd"
            template.write_bytes(b"")
            destination.parent.mkdir()
            with self.assertRaises(ValueError):
                copy_ovmf_vars_template(template, destination)

    def test_actual_cli_copy_reads_vars_template_not_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            vars_template = root / "OVMF_VARS.fd"
            iso.write_bytes(b"non-empty test ISO")
            code.write_bytes(b"READ ONLY FIRMWARE CODE")
            vars_template.write_bytes(b"UEFI VARIABLE STORE TEMPLATE")
            copied = {}
            original_copyfile = qemu_boot_smoke.shutil.copyfile

            def capture_copy(source, destination):
                result = original_copyfile(source, destination)
                copied["source"] = Path(source).read_bytes()
                copied["destination"] = Path(destination).read_bytes()
                return result

            output = io.StringIO()
            with mock.patch.object(
                qemu_boot_smoke.shutil, "copyfile", side_effect=capture_copy
            ):
                with contextlib.redirect_stdout(output):
                    status = qemu_boot_smoke.main([
                        "--iso", str(iso), "--firmware", "uefi",
                        "--ovmf-code", str(code), "--ovmf-vars", str(vars_template),
                        "--dry-run",
                    ])

            self.assertEqual(status, 0)
            self.assertEqual(copied["source"], vars_template.read_bytes())
            self.assertEqual(copied["destination"], vars_template.read_bytes())
            self.assertNotEqual(copied["destination"], code.read_bytes())
            payload = json.loads(output.getvalue())
            command = " ".join(payload["qemu_command"])
            self.assertIn("unit=0,readonly=on", command)
            self.assertIn("unit=1", command)
            self.assertFalse(payload["host_efi_variables_modified"])
            self.assertTrue(payload["guest_uefi_vars_writable"])
            self.assertEqual(payload["guest_uefi_vars_source"], "private-copy-of-vars-template")
            self.assertEqual(code.read_bytes(), b"READ ONLY FIRMWARE CODE")
            self.assertEqual(vars_template.read_bytes(), b"UEFI VARIABLE STORE TEMPLATE")

    def test_uefi_cli_uses_code_and_private_copy_of_distinct_vars_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code = root / "OVMF_CODE.fd"
            vars_template = root / "OVMF_VARS.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code.write_bytes(b"code bytes are not vars")
            vars_template.write_bytes(b"vars bytes are distinct from code")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code), "--ovmf-vars", str(vars_template),
                "--dry-run",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        command = payload["qemu_command"]
        drives = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-drive"]
        self.assertEqual(len(drives), 2)
        self.assertIn(f"file={code}", drives[0])
        self.assertIn("unit=0", drives[0])
        self.assertIn("readonly=on", drives[0])
        self.assertIn("OVMF_VARS.fd", drives[1])
        self.assertIn("unit=1", drives[1])
        self.assertNotIn(f"file={vars_template}", drives[1])
        self.assertNotIn("readonly=on", drives[1])
        self.assertFalse(payload["host_efi_variables_modified"])
        self.assertTrue(payload["guest_uefi_vars_writable"])
        self.assertEqual(payload["guest_uefi_vars_source"], "private-copy-of-vars-template")

    def test_uefi_rejects_using_the_same_file_for_code_and_vars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "live.iso"
            code_and_vars = root / "OVMF.fd"
            iso.write_bytes(b"not really an iso, but not empty")
            code_and_vars.write_bytes(b"one file cannot be both firmware code and vars")
            result = self.run_harness(
                "--iso", str(iso), "--firmware", "uefi",
                "--ovmf-code", str(code_and_vars), "--ovmf-vars", str(code_and_vars),
                "--dry-run",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be separate files", result.stderr)

    def test_dry_run_reports_bios_without_guest_nvram(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
            iso.write(b"not really an iso, but not empty")
            iso.flush()
            result = self.run_harness("--iso", iso.name, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["firmware"], "bios")
        self.assertFalse(payload["host_efi_variables_modified"])
        self.assertFalse(payload["guest_uefi_vars_writable"])

    def test_acceptance_document_uses_builder_output_path_and_make_target(self) -> None:
        builder = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "DESKTOP-PROFILE.md").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn('ISO_OUTPUT="$OUTPUT_DIR/wsm-desktop-live.iso"', builder)
        self.assertIn("--iso build/wsm-desktop-live.iso", docs)
        self.assertNotIn("--iso build/wsm-desktop.iso", docs)
        self.assertIn("image-live:", makefile)
        self.assertIn("./scripts/build_iso.sh", makefile)
        self.assertIn("make image-live", docs)


if __name__ == "__main__":
    unittest.main()
