# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety and command-construction tests for the disposable QEMU harness."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.qemu_boot_smoke import build_qemu_command, main, validate_iso


class QemuBootSmokeTests(unittest.TestCase):
    def test_command_uses_only_disposable_disk_and_disables_host_io_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            iso = root / "live.iso"
            qcow2 = root / "temporary" / "disk.qcow2"
            serial = root / "temporary" / "serial.log"
            iso.write_bytes(b"synthetic ISO placeholder")
            command = build_qemu_command("qemu-system-x86_64", iso, qcow2, serial, 2048, 2)
            joined = " ".join(command)
            self.assertIn("accel=tcg", joined)
            self.assertIn(f"file={qcow2},if=virtio,format=qcow2", joined)
            self.assertIn("-nic none", joined)
            self.assertNotIn("/dev/sd", joined)
            self.assertNotIn("/dev/nvme", joined)
            self.assertNotIn("host=", joined)
            self.assertNotIn("if=none", joined)
            self.assertFalse(any("pflash" in item or "efi" in item.lower() for item in command))

    def test_validate_iso_rejects_directory_and_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                validate_iso(root)
            empty = root / "empty.iso"
            empty.touch()
            with self.assertRaises(ValueError):
                validate_iso(empty)

    def test_validate_iso_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "image.iso"
            target.write_bytes(b"iso")
            link = root / "link.iso"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                validate_iso(link)

    def test_dry_run_reports_no_passthrough_or_guest_installer_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--dry-run"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mode"], "dry-run")
            self.assertFalse(payload["host_device_passthrough"])
            self.assertFalse(payload["network_enabled"])
            self.assertFalse(payload["efi_variable_store"])
            self.assertFalse(payload["guest_installer_execution"])
            self.assertIn("disposable.qcow2", payload["qcow2_path"])

    def test_invalid_disk_size_fails_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main(["--iso", str(iso), "--disk-size", "/dev/sda"])
            self.assertEqual(result, 2)
            self.assertIn("positive size", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
