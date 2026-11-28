# SPDX-License-Identifier: LicenseRef-Volnist
"""Compile, run and schema-validate the FPC collector against synthetic sysfs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # The fast CI installs jsonschema; keep the test's failure explicit.
    Draft202012Validator = None
    FormatChecker = None

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "pascal" / "wsm_hwcheck.pas"
SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"


@unittest.skipUnless(shutil.which("fpc"), "FPC is absent; native behaviour is not verified")
class FpcRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if Draft202012Validator is None:
            raise RuntimeError("jsonschema is required to validate FPC output")
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-")
        cls.build_dir = Path(cls.temporary.name) / "build"
        cls.build_dir.mkdir()
        cls.binary = cls.build_dir / "wsm-hwcheck"
        compiled = subprocess.run(
            [
                shutil.which("fpc") or "fpc",
                "-Mobjfpc",
                "-Sh",
                "-O2",
                f"-FE{cls.build_dir}",
                f"-FU{cls.build_dir}",
                f"-o{cls.binary}",
                str(SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if compiled.returncode != 0 or not cls.binary.is_file():
            raise RuntimeError(
                "FPC failed to compile wsm_hwcheck.pas\n"
                f"stdout:\n{compiled.stdout}\nstderr:\n{compiled.stderr}"
            )
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema, format_checker=FormatChecker()
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def make_roots(self, *, with_pci: bool) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp(prefix="sysfs-"))
        proc = Path(tempfile.mkdtemp(prefix="procfs-"))
        (root / "bus" / "pci" / "devices").mkdir(parents=True)
        (root / "firmware" / "efi").mkdir(parents=True)
        (root / "class" / "dmi" / "id").mkdir(parents=True)
        (proc / "sys" / "kernel").mkdir(parents=True)
        (proc / "sys" / "kernel" / "osrelease").write_text(
            "6.18.58.1-test\n", encoding="ascii"
        )
        if with_pci:
            device = root / "bus" / "pci" / "devices" / "0000:00:02.0"
            device.mkdir()
            (device / "vendor").write_text("0x8086\n", encoding="ascii")
            (device / "device").write_text("0x1902\n", encoding="ascii")
            (device / "subsystem_vendor").write_text("0x1458\n", encoding="ascii")
            (device / "subsystem_device").write_text("0x5000\n", encoding="ascii")
            (device / "revision").write_text("0x06\n", encoding="ascii")
            (device / "class").write_text("0x030000\n", encoding="ascii")
            # A quote in the link basename proves JSON escaping at runtime.
            os.symlink("/sys/bus/pci/drivers/test\"driver", device / "driver")
        return root, proc

    def run_collector(self, sysfs_root: Path, proc_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(self.binary),
                "--sysfs-root", str(sysfs_root),
                "--proc-root", str(proc_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_schema_valid(self, payload: dict) -> None:
        errors = sorted(
            self.validator.iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(
            errors,
            [],
            "\n".join(
                f"{list(error.absolute_path)}: {error.message}" for error in errors
            ),
        )

    def test_pci_identity_json_matches_report_1_1_schema(self) -> None:
        sysfs_root, proc_root = self.make_roots(with_pci=True)
        try:
            completed = self.run_collector(sysfs_root, proc_root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assert_schema_valid(payload)
            self.assertEqual(payload["schema_version"], "1.1.0")
            self.assertEqual(payload["environment"]["kernel_release"], "6.18.58.1-test")
            self.assertEqual(payload["environment"]["boot_mode"], "uefi")
            self.assertEqual(len(payload["devices"]), 1)
            device = payload["devices"][0]
            self.assertEqual(device["category"], "gpu")
            self.assertEqual(device["identity"]["vendor_id"], "8086")
            self.assertEqual(device["identity"]["device_id"], "1902")
            self.assertEqual(device["identity"]["class_id"], "030000")
            self.assertEqual(device["driver"]["status"], "bound")
            self.assertEqual(device["driver"]["bound_driver"], 'test"driver')
        finally:
            shutil.rmtree(sysfs_root, ignore_errors=True)
            shutil.rmtree(proc_root, ignore_errors=True)

    def test_empty_pci_inventory_is_valid_json_with_nonzero_status(self) -> None:
        sysfs_root, proc_root = self.make_roots(with_pci=False)
        try:
            completed = self.run_collector(sysfs_root, proc_root)
            self.assertEqual(completed.returncode, 4, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assert_schema_valid(payload)
            self.assertEqual(payload["devices"], [])
            self.assertTrue(payload["warnings"])
        finally:
            shutil.rmtree(sysfs_root, ignore_errors=True)
            shutil.rmtree(proc_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
