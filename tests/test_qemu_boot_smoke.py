# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety and command-construction tests for the disposable QEMU harness."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qemu_boot_smoke import (
    MAX_CPUS,
    MAX_DISK_MIB,
    MAX_MEMORY_MIB,
    MAX_TIMEOUT_SECONDS,
    MAX_BOOT_MARKER_BYTES,
    MAX_SERIAL_CAPTURE_BYTES,
    MAX_STDERR_CAPTURE_BYTES,
    CAPTURE_CHUNK_BYTES,
    MIN_CPUS,
    MIN_DISK_MIB,
    MIN_MEMORY_MIB,
    MIN_TIMEOUT_SECONDS,
    _capture_stream,
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


    def test_serial_capture_keeps_bounded_tail_and_finds_early_marker(self) -> None:
        marker = b"WSM_EARLY_BOOT_MARKER"
        payload = marker + (b"x" * (MAX_SERIAL_CAPTURE_BYTES * 2))
        tail, truncated, marker_seen, total = _capture_stream(
            io.BytesIO(payload), max_bytes=256, marker_bytes=marker
        )
        self.assertEqual(len(tail), 256)
        self.assertEqual(tail, payload[-256:])
        self.assertTrue(truncated)
        self.assertTrue(marker_seen)
        self.assertEqual(total, len(payload))

    def test_serial_capture_detects_marker_across_read_boundary(self) -> None:
        marker = b"WSM_SPLIT_BOUNDARY_MARKER"
        payload = (b"a" * (CAPTURE_CHUNK_BYTES - 3)) + marker + (b"z" * 100)
        tail, truncated, marker_seen, total = _capture_stream(
            io.BytesIO(payload), max_bytes=128, marker_bytes=marker
        )
        self.assertTrue(marker_seen)
        self.assertTrue(truncated)
        self.assertEqual(total, len(payload))
        self.assertEqual(tail, payload[-128:])

    def test_stderr_capture_is_bounded_and_reports_truncation(self) -> None:
        payload = b"Q" * (MAX_STDERR_CAPTURE_BYTES + 4096)
        tail, truncated, marker_seen, total = _capture_stream(
            io.BytesIO(payload), max_bytes=MAX_STDERR_CAPTURE_BYTES
        )
        self.assertEqual(len(tail), MAX_STDERR_CAPTURE_BYTES)
        self.assertEqual(tail, payload[-MAX_STDERR_CAPTURE_BYTES:])
        self.assertTrue(truncated)
        self.assertFalse(marker_seen)
        self.assertEqual(total, len(payload))

    def test_capture_rejects_nonpositive_limit(self) -> None:
        with self.assertRaises(ValueError):
            _capture_stream(io.BytesIO(b"data"), max_bytes=0)

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

            class FakeProcess:
                def __init__(self):
                    self.serial_bytes = b"booting\nWSM-LIVE-READY\n" + (b"x" * (MAX_SERIAL_CAPTURE_BYTES + 100))
                    self.stderr_bytes = b"QEMU diagnostic\n" + (b"e" * (MAX_STDERR_CAPTURE_BYTES + 100))
                    self.stdout = io.BytesIO(self.serial_bytes)
                    self.stderr = io.BytesIO(self.stderr_bytes)
                    self.wait_calls = 0
                    self.killed = False

                def wait(self, timeout=None):
                    self.wait_calls += 1
                    if self.wait_calls == 1:
                        raise subprocess.TimeoutExpired(["qemu"], timeout)
                    return -9

                def kill(self):
                    self.killed = True

            fake_process = FakeProcess()

            def fake_run(command, **kwargs):
                calls.append(command)
                self.assertEqual(command[0], "qemu-img")
                Path(command[4]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            stdout = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), patch(
                "scripts.qemu_boot_smoke.subprocess.Popen", return_value=fake_process
            ) as popen, contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--boot-marker", "WSM-LIVE-READY"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["boot_confirmed"])
            self.assertTrue(payload["qemu_timed_out"])
            self.assertEqual(payload["qemu_returncode"], None)
            self.assertTrue(payload["serial_output_truncated"])
            self.assertTrue(payload["qemu_error_truncated"])
            self.assertLessEqual(len(payload["serial_output_tail"]), 4000)
            self.assertLessEqual(
                len(payload["qemu_error"].encode("utf-8")),
                MAX_STDERR_CAPTURE_BYTES,
            )
            self.assertEqual(payload["serial_output_bytes"], len(fake_process.serial_bytes))
            self.assertEqual(payload["qemu_error_bytes"], len(fake_process.stderr_bytes))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:4], ["create", "-f", "qcow2"])
            popen.assert_called_once()
            qemu_command = popen.call_args.args[0]
            self.assertEqual(qemu_command[qemu_command.index("-serial") + 1], "stdio")
            self.assertTrue(fake_process.killed)

    def test_oversized_boot_marker_is_rejected_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stderr = io.StringIO()
            with patch("scripts.qemu_boot_smoke.subprocess.run") as run, patch(
                "scripts.qemu_boot_smoke.subprocess.Popen"
            ) as popen, contextlib.redirect_stderr(stderr):
                result = main([
                    "--iso", str(iso),
                    "--boot-marker", "m" * (MAX_BOOT_MARKER_BYTES + 1),
                ])
            self.assertEqual(result, 2)
            run.assert_not_called()
            popen.assert_not_called()
            self.assertIn("boot marker exceeds", stderr.getvalue())

    @unittest.skipUnless(
        shutil.which("qemu-system-x86_64") and shutil.which("qemu-img"),
        "real QEMU CLI smoke requires qemu-system-x86_64 and qemu-img",
    )
    def test_real_qemu_accepts_generated_command_with_comma_path(self) -> None:
        """Start QEMU paused to validate real CLI parsing without booting a guest."""
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "tmp,comma"
            root.mkdir()
            iso = root / "synthetic.iso"
            qcow2 = root / "disposable.qcow2"
            iso.write_bytes(b"\\0" * 2048)
            subprocess.run(
                ["qemu-img", "create", "-f", "qcow2", str(qcow2), "256M"],
                check=True,
                capture_output=True,
                text=True,
            )

            command = build_qemu_command(
                "qemu-system-x86_64", iso, qcow2, 256, 1
            )
            # Pause the guest CPU so this test validates device/option setup only.
            command.insert(1, "-S")
            try:
                subprocess.run(
                    command,
                    check=False,
                    timeout=3,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                return
            self.fail("QEMU exited before the bounded paused-VM smoke timeout")


if __name__ == "__main__":
    unittest.main()
