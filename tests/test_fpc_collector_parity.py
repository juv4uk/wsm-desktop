# SPDX-License-Identifier: LicenseRef-Volnist
"""Parity between the FPC collector slice and the Python collector.

The point of the port is not "Pascal is nicer". It is two measurable things the
package pays today: ~62 ms of interpreter start on every invocation, and CPython
plus jsonschema in the closure (the package's own comment records that Python
builds were ~226 MB of a 399 MB pack).

This test therefore does not reward a rewrite that quietly changes behaviour. It
compiles the FPC slice and compares its output with the Python collector's own
values for the same machine. If FPC is absent it skips — and says so, because a
skipped parity test proves nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "fpc" / "wsm_hwcheck.pas"


class FpcCollectorParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fpc = shutil.which("fpc")
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def compile_slice(self) -> Path:
        """Build the slice; return the binary path."""
        output_dir = Path(self.temporary.name)
        completed = subprocess.run(
            [self.fpc, "-O2", f"-FE{output_dir}", f"-o{output_dir / 'wsm_hwcheck'}",
             str(SOURCE)],
            capture_output=True,
            text=True,
            check=False,
        )
        binary = output_dir / "wsm_hwcheck"
        self.assertTrue(
            binary.is_file(),
            f"FPC did not produce a binary.\nstdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}",
        )
        return binary

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; parity is NOT proven")
    def test_the_slice_builds(self) -> None:
        binary = self.compile_slice()
        self.assertTrue(binary.is_file())

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; parity is NOT proven")
    def test_the_slice_emits_json(self) -> None:
        binary = self.compile_slice()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["collector"], "wsm-hwcheck-pascal")
        self.assertIn("architecture", payload["environment"])
        self.assertIn("kernel_release", payload["environment"])
        self.assertIsInstance(payload["pci"], list)

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; parity is NOT proven")
    def test_pci_identity_matches_the_python_collector(self) -> None:
        """Same machine, same sysfs — the two implementations must agree."""
        sys.path.insert(0, str(ROOT))
        from wsm_hwcheck.collector import collect_report  # noqa: PLC0415

        python_report = collect_report()
        python_pci = {
            device.get("identity", {}).get("pci_address") or device.get("device_id"): device
            for device in python_report.get("devices", [])
            if device.get("bus") == "pci"
        }

        binary = self.compile_slice()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
        payload = json.loads(completed.stdout)
        pascal_pci = {device["address"]: device for device in payload["pci"]}

        self.assertEqual(
            set(pascal_pci),
            set(python_pci),
            "the two collectors disagree about which PCI devices exist",
        )
        for address, pascal_device in pascal_pci.items():
            python_device = python_pci[address]
            identity = python_device.get("identity", {})
            self.assertEqual(pascal_device["vendor"], identity.get("vendor_id", ""))
            self.assertEqual(pascal_device["device"], identity.get("device_id", ""))
            self.assertEqual(pascal_device["class"], identity.get("class_id", ""))
            # Driver binding is the fact the GPU certification question turns on.
            python_driver = python_device.get("driver", {})
            self.assertEqual(
                pascal_device["driver"]["status"], python_driver.get("status", ""),
                f"{address}: driver status disagrees",
            )
            if pascal_device["driver"]["status"] == "bound":
                self.assertEqual(
                    pascal_device["driver"]["bound_driver"],
                    python_driver.get("bound_driver", ""),
                    f"{address}: bound driver disagrees",
                )

    def test_the_source_says_it_was_not_compiled_where_it_was_written(self) -> None:
        """The file must not pretend to be verified."""
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("НЕ ЗІБРАНО", text)


if __name__ == "__main__":
    unittest.main()
