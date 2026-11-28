# SPDX-License-Identifier: LicenseRef-Volnist
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
    MIN_CPUS,
    MIN_DISK_MIB,
    MIN_MEMORY_MIB,
    MIN_TIMEOUT_SECONDS,
    BoundedProcessResult,
    MAX_BOOT_MARKER_BYTES,
    MAX_SERIAL_CAPTURE_BYTES,
    MAX_STDERR_CAPTURE_BYTES,
    build_qemu_command,
    main,
    sha256_of,
    parse_disk_size_mib,
    run_bounded_process,
    validate_iso,
    validate_limits,
)


class QemuBootSmokeTests(unittest.TestCase):
    def test_default_capture_limits_are_explicit(self) -> None:
        self.assertEqual(MAX_SERIAL_CAPTURE_BYTES, 1024 * 1024)
        self.assertEqual(MAX_STDERR_CAPTURE_BYTES, 256 * 1024)
        self.assertLessEqual(MAX_BOOT_MARKER_BYTES, 1024)

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
                Path(command[4]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            captured = BoundedProcessResult(
                returncode=None,
                timed_out=True,
                stdout_tail=b"booting\nWSM-LIVE-READY\n",
                stderr_tail=b"bounded warning",
                stdout_bytes_seen=24,
                stderr_bytes_seen=15,
                stdout_truncated=False,
                stderr_truncated=False,
                marker_seen=True,
            )
            stdout = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), patch("scripts.qemu_boot_smoke.run_bounded_process", return_value=captured) as runner, contextlib.redirect_stdout(stdout):
                result = main(["--iso", str(iso), "--boot-marker", "WSM-LIVE-READY"])
            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["iso_sha256"], sha256_of(iso))
            self.assertTrue(payload["boot_confirmed"])
            self.assertTrue(payload["qemu_timed_out"])
            self.assertEqual(payload["serial_output_tail"], "booting\nWSM-LIVE-READY\n")
            self.assertEqual(payload["qemu_error"], "bounded warning")
            self.assertFalse(payload["serial_truncated"])
            self.assertFalse(payload["stderr_truncated"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:4], ["create", "-f", "qcow2"])
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["marker"], "WSM-LIVE-READY")

    def test_runtime_fails_when_boot_marker_follows_guest_segfault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")

            def fake_run(command, **kwargs):
                Path(command[4]).touch()
                return subprocess.CompletedProcess(command, 0, "", "")

            captured = BoundedProcessResult(
                returncode=None,
                timed_out=True,
                stdout_tail=b"init[1]: segfault at 3fff00\nWSM-LIVE-READY\n",
                stderr_tail=b"",
                stdout_bytes_seen=48,
                stderr_bytes_seen=0,
                stdout_truncated=False,
                stderr_truncated=False,
                marker_seen=True,
                failure_markers_seen=("segfault",),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("scripts.qemu_boot_smoke.shutil.which", side_effect=lambda name: name), patch(
                "scripts.qemu_boot_smoke.subprocess.run", side_effect=fake_run
            ), patch("scripts.qemu_boot_smoke.run_bounded_process", return_value=captured), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["--iso", str(iso), "--boot-marker", "WSM-LIVE-READY"])

            self.assertEqual(result, 5)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["boot_confirmed"])
            self.assertFalse(payload["serial_clean"])
            self.assertEqual(payload["serial_failure_markers"], ["segfault"])
            self.assertIn("fatal kernel/userspace crash signals", stderr.getvalue())

    def test_bounded_capture_detects_marker_before_retained_tail(self) -> None:
        marker = "WSM_MARKER_AT_STREAM_START"
        child = (
            "import sys\n"
            f"sys.stdout.buffer.write({marker.encode()!r} + b'S' * 200000)\n"
            "sys.stdout.flush()\n"
            "sys.stderr.buffer.write(b'E' * 100000)\n"
            "sys.stderr.flush()\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=5,
            marker=marker,
            max_stdout_bytes=1024,
            max_stderr_bytes=512,
            read_chunk_bytes=257,
        )
        self.assertFalse(result.timed_out)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.marker_seen)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertEqual(len(result.stdout_tail), 1024)
        self.assertEqual(len(result.stderr_tail), 512)
        self.assertGreater(result.stdout_bytes_seen, 200000)
        self.assertEqual(result.stderr_bytes_seen, 100000)
        self.assertNotIn(marker.encode(), result.stdout_tail)

    def test_bounded_capture_detects_marker_split_across_reads(self) -> None:
        marker = "SPLIT-MARKER-BOUNDARY"
        child = (
            "import os, sys, time\n"
            "os.write(1, b'prefix-SPLIT-')\n"
            "time.sleep(0.05)\n"
            "os.write(1, b'MARKER-BOUNDARY-suffix')\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=5,
            marker=marker,
            max_stdout_bytes=8,
            max_stderr_bytes=8,
            read_chunk_bytes=3,
        )
        self.assertTrue(result.marker_seen)
        self.assertTrue(result.stdout_truncated)
        self.assertLessEqual(len(result.stdout_tail), 8)

    def test_bounded_capture_detects_serial_segfault_split_across_reads(self) -> None:
        child = (
            "import os, time\n"
            "os.write(1, b'init[1]: segf')\n"
            "time.sleep(0.05)\n"
            "os.write(1, b'ault at 3fff00\nWSM_LIVE_READY\n' + b'X' * 2048)\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=5,
            marker="WSM_LIVE_READY",
            max_stdout_bytes=64,
            max_stderr_bytes=32,
            read_chunk_bytes=3,
        )
        self.assertTrue(result.marker_seen)
        self.assertEqual(result.failure_markers_seen, ("segfault",))
        self.assertTrue(result.stdout_truncated)
        self.assertLessEqual(len(result.stdout_tail), 64)
        self.assertNotIn(b"segfault", result.stdout_tail)

    def test_bounded_capture_kills_noisy_child_after_timeout(self) -> None:
        child = (
            "import os, time\n"
            "chunk = b'X' * 8192\n"
            "while True:\n"
            "    os.write(1, chunk)\n"
            "    os.write(2, chunk)\n"
        )
        result = run_bounded_process(
            [sys.executable, "-c", child],
            timeout_seconds=0.2,
            marker="NEVER-SEEN",
            max_stdout_bytes=2048,
            max_stderr_bytes=1024,
            read_chunk_bytes=512,
        )
        self.assertTrue(result.timed_out)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertLessEqual(len(result.stdout_tail), 2048)
        self.assertLessEqual(len(result.stderr_tail), 1024)
        self.assertGreater(result.stdout_bytes_seen, 2048)
        self.assertGreater(result.stderr_bytes_seen, 1024)
        self.assertFalse(result.marker_seen)

    def test_oversized_boot_marker_is_rejected_before_qemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "live.iso"
            iso.write_bytes(b"synthetic ISO placeholder")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("scripts.qemu_boot_smoke.subprocess.run") as run, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main([
                    "--iso", str(iso),
                    "--boot-marker", "M" * (MAX_BOOT_MARKER_BYTES + 1),
                ])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertIn("boot marker must be no more than", stderr.getvalue())

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
