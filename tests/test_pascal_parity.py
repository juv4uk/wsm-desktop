# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC binary and the Python collector must agree about the same machine.

Two implementations of one report are worth nothing until something compares
them. This test compiles the Pascal program, runs it, runs the Python collector
on the same sysfs, and compares the fields both are supposed to emit.

It runs where a compiler exists — the ``Free Pascal build`` workflow, which
installs fpc 3.2.2. Elsewhere it skips, and says so: a skipped parity test
proves nothing, and a green run without a compiler would be exactly the kind of
empty gate this repository keeps having to remove.

Comparison is by device set and field values, not by text: the two write JSON
differently on purpose (the native one writes it by hand), so text equality
would test formatting rather than meaning.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "pascal" / "wsm_hwcheck.pas"


def python_pci_devices() -> dict[str, dict]:
    """PCI devices as the Python collector reports them, keyed by sysfs address."""
    import sys

    sys.path.insert(0, str(ROOT))
    from wsm_hwcheck.collector import collect_report  # noqa: PLC0415

    report = collect_report()
    devices: dict[str, dict] = {}
    for device in report.get("devices", []):
        if device.get("bus") != "pci":
            continue
        identity = device.get("identity") or {}
        local_path = identity.get("local_path", "")
        address = local_path.rsplit("/", 1)[-1]
        if address:
            devices[address] = device
    return devices


class PascalParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fpc = shutil.which("fpc")
        cls.temporary = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def compile_program(self) -> Path:
        output_dir = Path(self.temporary.name)
        completed = subprocess.run(
            [
                self.fpc,
                "-O2",
                "-Mobjfpc",
                "-Sh",
                f"-FU{output_dir}",
                f"-FE{output_dir}",
                f"-Fu{SOURCE.parent}",
                str(SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        binary = output_dir / "wsm_hwcheck"
        self.assertTrue(
            binary.is_file(),
            f"fpc produced no binary\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return binary

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; parity is NOT proven")
    def test_the_program_emits_parseable_json(self) -> None:
        binary = self.compile_program()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload.get("devices"), list)

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; parity is NOT proven")
    def test_it_reports_the_same_pci_devices_as_python(self) -> None:
        binary = self.compile_program()
        completed = subprocess.run([str(binary)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)

        pascal_devices = {}
        for device in payload.get("devices", []):
            if device.get("bus") != "pci":
                continue
            identity = device.get("identity") or {}
            address = (identity.get("local_path") or "").rsplit("/", 1)[-1]
            if address:
                pascal_devices[address] = device

        expected = python_pci_devices()
        if not expected:
            self.skipTest(
                "no PCI devices on this host: an empty list on both sides would "
                "pass without comparing a single field"
            )

        self.assertEqual(
            set(pascal_devices),
            set(expected),
            "the two collectors disagree about which PCI devices exist",
        )

        for address, python_device in expected.items():
            pascal_device = pascal_devices[address]
            pascal_identity = pascal_device.get("identity") or {}
            python_identity = python_device.get("identity") or {}
            with self.subTest(address=address):
                self.assertEqual(pascal_device.get("device_id"), python_device.get("device_id"))
                self.assertEqual(pascal_identity.get("vendor_id"), python_identity.get("vendor_id"))
                self.assertEqual(pascal_identity.get("device_id"), python_identity.get("device_id"))
                self.assertEqual(
                    pascal_device.get("driver", {}).get("status"),
                    python_device.get("driver", {}).get("status"),
                    "driver status is the fact the certification question turns on",
                )

    def test_the_source_is_present(self) -> None:
        self.assertTrue(SOURCE.is_file(), "the Pascal program moved; update this test")


if __name__ == "__main__":
    unittest.main()
