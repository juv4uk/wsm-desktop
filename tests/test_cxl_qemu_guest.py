# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety tests for the disposable QEMU CXL guest topology probe."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ci_cxl_qemu_guest as guest
from scripts.ci_cxl_qemu_guest import build_qemu_command, parse_insmod_plan, summarize_guest_serial


class QemuCxlGuestTests(unittest.TestCase):
    def test_guest_uses_volatile_type3_and_no_host_io_paths(self) -> None:
        command = build_qemu_command("qemu", Path("/tmp/vmlinuz"), Path("/tmp/initrd"))
        self.assertIn("q35,cxl=on", command)
        self.assertIn(
            "cxl-type3,bus=root_port0,volatile-memdev=vmem0,id=cxl-vmem0",
            command,
        )
        self.assertIn("-accel", command)
        self.assertEqual(command[command.index("-accel") + 1], "tcg")
        self.assertIn("-no-user-config", command)
        self.assertIn("-nodefaults", command)
        self.assertIn("-nic", command)
        self.assertEqual(command[command.index("-nic") + 1], "none")
        self.assertNotIn("-drive", command)
        self.assertNotIn("-cdrom", command)
        self.assertFalse(any("host=" in token for token in command))

    def test_module_plan_accepts_only_paths_inside_selected_kernel_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "cxl_core.ko"
            module.write_bytes(b"synthetic")
            plan = parse_insmod_plan(f"insmod {module}\nbuiltin pci", root)
            self.assertEqual(plan, [module.resolve()])

    def test_module_plan_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            module = Path(outside) / "evil.ko"
            module.write_bytes(b"synthetic")
            with self.assertRaises(Exception):
                parse_insmod_plan(f"insmod {module}", root)

    def test_capture_and_initramfs_have_explicit_limits(self) -> None:
        source = (ROOT / "scripts" / "ci_qemu_cxl_guest.py").read_text(encoding="utf-8")
        self.assertIn("run_bounded_process", source)
        self.assertIn("MAX_INITRAMFS_BYTES", source)
        self.assertIn("MAX_MODULE_TOTAL_BYTES", source)

    def test_failure_path_does_not_emit_raw_dmesg_or_sysfs_listing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guest.write_guest_init(root, [])
            init = (root / "init").read_text(encoding="utf-8")
        self.assertNotIn("dmesg", init)
        self.assertNotIn("ls -l /sys/bus/cxl/devices", init)
        self.assertIn("WSM_CXL_FAILURE_DIAGNOSTICS=redacted", init)
    def test_failure_summary_does_not_echo_raw_console_or_pci_addresses(self) -> None:
        raw = (
            "PCI: 0000:00:1f.0 EDID parser failure\n"
            "WSM_CXL_STAGE_MODULE_LOAD\n"
            "WSM_CXL_COUNTS devices=8 ports=4 memdevs=1 edges=7\n"
            "WSM_CXL_STATUS=type3-memdev-discovered\n"
        )
        summary = summarize_guest_serial(raw)
        self.assertIn("WSM_CXL_STAGE_MODULE_LOAD", summary)
        self.assertIn("type3-memdev-discovered", summary)
        self.assertIn("devices=8,ports=4,memdevs=1,edges=7", summary)
        self.assertNotIn("0000:00:1f.0", summary)
        self.assertNotIn("EDID", summary)
        self.assertNotIn("PCI", summary)

        untrusted = summarize_guest_serial(
            "WSM_CXL_STATUS=0000:00:1f.0\n"
            "WSM_CXL_COUNTS devices=8 ports=4 memdevs=1 edges=7 PCI=secret\n"
        )
        self.assertIn("status=unknown", untrusted)
        self.assertIn("counts=not-reported", untrusted)
        self.assertNotIn("0000:00:1f.0", untrusted)
        self.assertNotIn("secret", untrusted)

    def test_sysfs_report_uses_synthetic_names_not_host_addresses(self) -> None:
        source = (ROOT / "scripts" / "ci_qemu_cxl_guest.py").read_text(encoding="utf-8")
        self.assertIn("device_pattern.fullmatch", source)
        self.assertIn("edge_pattern.fullmatch", source)
        self.assertNotIn("HPA", source)
        self.assertNotIn("DPA", source)


    def test_module_decompression_rejects_stream_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cxl_core.ko.xz"
            source.write_bytes(b"compressed")
            result = SimpleNamespace(
                timed_out=False,
                stdout_truncated=True,
                returncode=0,
                stdout_tail=b"x" * 1024,
            )
            with patch("scripts.ci_cxl_qemu_guest.run_bounded_process", return_value=result) as runner:
                with self.assertRaisesRegex(guest.CxlGuestError, "decompressed module exceeded"):
                    guest.decompress_module(source, 1024)
            self.assertLessEqual(runner.call_args.kwargs["max_stdout_bytes"], 1024)

    def test_initramfs_streaming_enforces_hard_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "archive.cpio.gz"
            command = [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'X' * 8192)",
            ]
            with self.assertRaisesRegex(guest.CxlGuestError, "exceeded the 1024-byte ceiling"):
                guest.run_bounded_file(
                    command,
                    cwd=root,
                    destination=destination,
                    timeout_seconds=5,
                    max_bytes=1024,
                )
            self.assertFalse(destination.exists())

    def test_initramfs_streaming_does_not_delete_preexisting_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "archive.cpio.gz"
            destination.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                guest.run_bounded_file(
                    [sys.executable, "-c", "print('unused')"],
                    cwd=root,
                    destination=destination,
                    timeout_seconds=5,
                    max_bytes=1024,
                )
            self.assertEqual(destination.read_bytes(), b"keep")

    def test_guest_serial_runner_has_explicit_capture_caps(self) -> None:
        self.assertEqual(guest.MAX_SERIAL_BYTES, 64 * 1024)
        self.assertEqual(guest.MAX_STDERR_BYTES, 32 * 1024)


if __name__ == "__main__":
    unittest.main()