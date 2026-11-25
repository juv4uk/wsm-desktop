# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety and command-construction tests for the disposable QEMU harness."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.qemu_boot_smoke import (
    MAX_CPUS,
    MAX_DISK_MIB,
    MAX_MEMORY_MIB,
    MAX_TIMEOUT_SECONDS,
    MIN_CPUS,
    MIN_DISK_MIB,
    MIN_MEMORY_MIB,
    MIN_TIMEOUT_SECONDS,
    build_qemu_command,
    main,
    parse_disk_size_mib,
    validate_iso,
    validate_limits,
)


class QemuBootSmokeTests(unittest.TestCase):
    def test_command_uses_json_for_paths_and_disables_host_io_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            iso = root / "live.iso"
            qcow2 = root / "tmp,comma" / "disk.qcow2"
            serial = root / "tmp,comma" / "serial.log"
            iso.write_bytes(b"synthetic ISO placeholder")
            command = build_qemu_command("qemu-system-x86_64", iso, qcow2, 2048, 2)

            blockdev_args = [
                json.loads(command[index + 1])
                for index, item in enumerate(command[:-1])
                if item == "-blockdev"
            ]

            self.assertEqual(blockdev_args[0]["filename"], str(qcow2))
            self.assertEqual(blockdev_args[1]["file"], "wsm-disk-file")
            self.assertEqual(command[command.index("-serial") + 1], "stdio")
            self.assertNotIn("-chardev", command)
            self.assertIn("-nic", command)
            self.assertEqual(command[command.index("-nic") + 1], "none")
            self.assertIn("accel=tcg", " ".join(command))
            self.assertNotIn("/dev/sd", " ".join(command))
            self.assertNotIn("/dev/nvme", " ".join(command))
            self.assertNotIn("host=", " ".join(command))
            self.assertFalse(any("pflash" in item or "efi" in item.lower() for item in command))

    def test_comma_in_temporary_root_is_preserved_in_json_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            comma_root = Path(parent) / "tmp,comma"
            comma_root.mkdir()
            iso = Path(parent) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            real_tempdir = tempfile.TemporaryDirectory

            with patch(
                "scripts.qemu_boot_smoke.tempfile.TemporaryDirectory",
                side_effect=lambda prefix: real_tempdir(prefix=prefix, dir=comma_root),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    result = main(["--iso", str(iso), "--dry-run"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            command = payload["qemu_command"]
            blockdev = [
                json.loads(command[index + 1])
                for index, item in enumerate(command[:-1])
                if item == "-blockdev"
            ]
            self.assertIn("tmp,comma", blockdev[0]["filename"])
            self.assertEqual(command[command.index("-serial") + 1], "stdio")
            self.assertNotIn("tmp,comma", command)

    def test_resource_limits_accept_all_documented_edges(self) -> None:
        validate_limits(MIN_TIMEOUT_SECONDS, MIN_MEMORY_MIB, MIN_CPUS, f"{MIN_DISK_MIB}M")
        validate_limits(MAX_TIMEOUT_SECONDS, MAX_MEMORY_MIB, MAX_CPUS, f"{MAX_DISK_MIB // 1024}G")

    def test_resource_limits_reject_values_outside_each_edge(self) -> None:
        invalid_cases = [
            (MIN_TIMEOUT_SECONDS - 1, 2048, 2, "4G"),
            (MAX_TIMEOUT_SECONDS + 1, 2048, 2, "4G"),
            (120, MIN_MEMORY_MIB - 1, 2, "4G"),
            (120, MAX_MEMORY_MIB + 1, 2, "4G"),
            (120, 2048, MIN_CPUS - 1, "4G"),
            (120, 2048, MAX_CPUS + 1, "4G"),
            (120, 2048, 2, f"{MIN_DISK_MIB - 1}M"),
            (120, 2048, 2, f"{MAX_DISK_MIB // 1024 + 1}G"),
            (120, 2048, 2, "1T"),
        ]
        for values in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    validate_limits(*values)

    def test_parse_disk_size_supports_equivalent_units(self) -> None:
        self.assertEqual(parse_disk_size_mib("1G"), 1024)
        self.assertEqual(parse_disk_size_mib("1024M"), 1024)
        self.assertEqual(parse_disk_size_mib("64G"), MAX_DISK_MIB)

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

    def test_invalid_resource_request_fails_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            with patch("scripts.qemu_boot_smoke.subprocess.run") as run:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = main(["--iso", str(iso), "--memory-mib", str(MAX_MEMORY_MIB + 1)])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertIn("memory must be between", stderr.getvalue())

    def test_runtime_confirms_only_explicit_serial_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                if command[0] == "qemu-img":
                    Path(command[4]).touch()
                    return subprocess.CompletedProcess(command, 0, "", "")
                self.assertEqual(command[command.index("-serial") + 1], "stdio")
                kwargs["stdout"].write("booting\\nWSM-LIVE-READY\\n")
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

            stdout = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--boot-marker", "WSM-LIVE-READY"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["boot_confirmed"])
            self.assertTrue(payload["qemu_timed_out"])
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][1:4], ["create", "-f", "qcow2"])
            self.assertIn("-nic", calls[1])
            self.assertIn("none", calls[1])


if __name__ == "__main__":
    unittest.main()
