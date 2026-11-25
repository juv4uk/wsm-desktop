# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-side safety tests for the disposable CXL QEMU guest probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wsm_cxl_qemu_guest_probe",
    ROOT / "scripts" / "ci_cxl_qemu_guest.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the CXL guest probe module")
guest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guest
SPEC.loader.exec_module(guest)


class GuestModuleCopyTests(unittest.TestCase):
    def test_uncompressed_module_stops_at_remaining_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "cxl_core.ko"
            destination = root / "out" / "cxl_core.ko"
            source.write_bytes(b"x" * 1024)

            with self.assertRaisesRegex(guest.ProbeError, "remaining 128-byte budget"):
                guest.copy_module(source, destination, max_output_bytes=128)

            self.assertFalse(destination.exists())

    def test_compressed_module_stops_at_expanded_budget_without_buffering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "cxl_core.ko.zst"
            destination = root / "out" / "cxl_core.ko"
            source.write_bytes(b"small compressed input")
            real_popen = subprocess.Popen
            processes: list[subprocess.Popen[bytes]] = []

            def fake_popen(_command, **kwargs):
                process = real_popen(
                    [
                        sys.executable,
                        "-c",
                        "import sys;\\nwhile True:\\n sys.stdout.buffer.write(b'x' * 65536); sys.stdout.buffer.flush()",
                    ],
                    **kwargs,
                )
                processes.append(process)
                return process

            with (
                patch.object(guest.shutil, "which", return_value=sys.executable),
                patch.object(guest.subprocess, "Popen", side_effect=fake_popen),
            ):
                with self.assertRaisesRegex(guest.ProbeError, "exceeds remaining 128-byte budget"):
                    guest.copy_module(source, destination, max_output_bytes=128)

            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())
            self.assertFalse(destination.exists())

    def test_compressed_module_timeout_terminates_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "cxl_core.ko.xz"
            destination = root / "out" / "cxl_core.ko"
            source.write_bytes(b"small compressed input")
            real_popen = subprocess.Popen
            processes: list[subprocess.Popen[bytes]] = []

            def fake_popen(_command, **kwargs):
                process = real_popen(
                    [sys.executable, "-c", "import time; time.sleep(20)"],
                    **kwargs,
                )
                processes.append(process)
                return process

            with (
                patch.object(guest.shutil, "which", return_value=sys.executable),
                patch.object(guest.subprocess, "Popen", side_effect=fake_popen),
                patch.object(guest, "MODULE_DECOMPRESS_TIMEOUT_SECONDS", 0.1),
            ):
                with self.assertRaisesRegex(guest.ProbeError, "timed out"):
                    guest.copy_module(source, destination, max_output_bytes=128)

            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())
            self.assertFalse(destination.exists())


class GuestReportTests(unittest.TestCase):
    def test_accepts_one_emulated_memdev(self) -> None:
        output = "\n".join(
            (
                "WSM_CXL_GUEST_BEGIN",
                "WSM_CXL_KERNEL=7.0.0-test",
                "WSM_CXL_NODE=root0",
                "WSM_CXL_NODE=port1",
                "WSM_CXL_NODE=mem0",
                "WSM_CXL_DEVTYPE=mem0:cxl_memdev",
                "WSM_CXL_NODE_COUNT=3",
                "WSM_CXL_MEMDEV_COUNT=1",
                "WSM_CXL_MODULE_FAILED=0",
                "WSM_CXL_GUEST_END",
            )
        )
        result = guest.parse_guest_output(output)
        self.assertEqual(result["nodes"], ["root0", "port1", "mem0"])
        self.assertEqual(result["devtypes"], ["mem0:cxl_memdev"])
        self.assertEqual(result["memdev_count"], 1)

    def test_rejects_missing_end_marker(self) -> None:
        with self.assertRaisesRegex(guest.ProbeError, "complete"):
            guest.parse_guest_output("WSM_CXL_GUEST_BEGIN\nWSM_CXL_MEMDEV_COUNT=1\n")

    def test_rejects_missing_memdev(self) -> None:
        output = "\n".join(
            (
                "WSM_CXL_GUEST_BEGIN",
                "WSM_CXL_NODE=root0",
                "WSM_CXL_NODE_COUNT=1",
                "WSM_CXL_MEMDEV_COUNT=0",
                "WSM_CXL_MODULE_FAILED=0",
                "WSM_CXL_GUEST_END",
            )
        )
        with self.assertRaisesRegex(guest.ProbeError, "did not enumerate"):
            guest.parse_guest_output(output)

    def test_rejects_module_load_failure(self) -> None:
        output = "\n".join(
            (
                "WSM_CXL_GUEST_BEGIN",
                "WSM_CXL_NODE=mem0",
                "WSM_CXL_MEMDEV_COUNT=1",
                "WSM_CXL_MODULE_LOAD_ERROR",
                "WSM_CXL_GUEST_END",
            )
        )
        with self.assertRaisesRegex(guest.ProbeError, "modules failed"):
            guest.parse_guest_output(output)

    def test_rejects_missing_required_module(self) -> None:
        output = "\n".join(
            (
                "WSM_CXL_GUEST_BEGIN",
                "WSM_CXL_NODE=mem0",
                "WSM_CXL_MEMDEV_COUNT=1",
                "WSM_CXL_MODULE_MISSING=cxl_pci",
                "WSM_CXL_MODULE_FAILED=1",
                "WSM_CXL_GUEST_END",
            )
        )
        with self.assertRaisesRegex(guest.ProbeError, "modules failed"):
            guest.parse_guest_output(output)

    def test_rejects_oversized_serial_capture(self) -> None:
        output = "x" * (guest.MAX_SERIAL_BYTES + 1)
        with self.assertRaisesRegex(guest.ProbeError, "64 KiB"):
            guest.parse_guest_output(output)


class GuestPolicyTests(unittest.TestCase):
    def test_guest_sysfs_mount_is_read_only(self) -> None:
        script = guest.render_init(["/lib/modules/test/kernel/drivers/cxl/cxl_core.ko"])
        self.assertIn("mount -t sysfs -o ro sysfs /sys", script)
        self.assertIn("mount -t proc -o ro proc /proc", script)
        self.assertNotIn("cxl create-region", script)
        self.assertNotIn("trigger_poison_list", script)
        self.assertNotIn("sanitize", script)
        self.assertNotIn("erase", script)
        self.assertNotIn("scrub", script)
        self.assertNotIn("setpci", script)

    def test_rendered_module_list_is_explicit(self) -> None:
        script = guest.render_init(
            [
                "/lib/modules/test/kernel/drivers/cxl/core/cxl_core.ko",
                "/lib/modules/test/kernel/drivers/cxl/cxl_pci.ko",
            ]
        )
        self.assertIn("/lib/modules/test/kernel/drivers/cxl/core/cxl_core.ko", script)
        self.assertIn("/lib/modules/test/kernel/drivers/cxl/cxl_pci.ko", script)
        self.assertIn("WSM_CXL_GUEST_END", script)


if __name__ == "__main__":
    unittest.main()
