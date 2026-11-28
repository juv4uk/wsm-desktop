# SPDX-License-Identifier: LicenseRef-Volnist
"""Compile the native FPC collector and check its WSM report contract.

The Python collector remains the current reference implementation. This suite
proves schema validity, read-only privacy declarations, and PCI identity parity
on the same Linux host. It does not claim complete feature parity: the FPC
report lists the diagnostics and topology stages that are still unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pascal"
SOURCE = SOURCE_DIR / "wsm_hwcheck.pas"
SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"


def nested_keys(value: object) -> set[str]:
    """Return every object key in a JSON document."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key).lower())
            found.update(nested_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(nested_keys(item))
    return found


class FpcCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fpc = shutil.which("fpc")
        if cls.fpc is None:
            raise unittest.SkipTest("FPC is not installed; native compile/parity is NOT proven")
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-test-")
        cls.build_dir = Path(cls.temporary.name)
        cls.binary = cls.build_dir / "wsm-hwcheck"
        command = [
            cls.fpc,
            "-B",
            "-O2",
            "-Mobjfpc",
            "-Sh",
            f"-Fu{SOURCE_DIR}",
            f"-FU{cls.build_dir}",
            f"-FE{cls.build_dir}",
            f"-o{cls.binary}",
            str(SOURCE),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not cls.binary.is_file():
            raise AssertionError(
                "FPC failed to compile the native collector.\n"
                f"command: {command!r}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def run_report(self, *args: str) -> dict:
        result = subprocess.run(
            [str(self.binary), *args, "--compact"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def validate_schema(self, report: dict) -> None:
        import jsonschema

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema, format_checker=jsonschema.FormatChecker())

    def test_cli_version_and_help(self) -> None:
        version = subprocess.run(
            [str(self.binary), "--version"], capture_output=True, text=True, check=False
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertEqual(version.stdout.strip(), "wsm-hwcheck 0.1.0")

        help_result = subprocess.run(
            [str(self.binary), "--help"], capture_output=True, text=True, check=False
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--sysfs-root", help_result.stdout)
        self.assertIn("--proc-root", help_result.stdout)

    def test_empty_sysfs_and_procfs_are_valid_unknown_evidence(self) -> None:
        empty_sys = self.build_dir / "empty-sys"
        empty_proc = self.build_dir / "empty-proc"
        empty_sys.mkdir(exist_ok=True)
        empty_proc.mkdir(exist_ok=True)
        report = self.run_report(
            "--sysfs-root", str(empty_sys), "--proc-root", str(empty_proc)
        )
        self.validate_schema(report)
        self.assertEqual(report["environment"]["boot_mode"], "unknown")
        self.assertEqual(report["environment"]["kernel_release"], "unknown")
        self.assertEqual(report["devices"], [])

    def test_host_report_validates_and_declares_strict_local_privacy(self) -> None:
        report = self.run_report()
        self.validate_schema(report)
        self.assertEqual(report["schema_version"], "1.1.0")
        self.assertEqual(report["collectors"][0]["name"], "wsm-hwcheck-fpc-sysfs")
        self.assertEqual(report["privacy"]["profile"], "strict-local")
        self.assertIs(report["privacy"]["network_upload_performed"], False)
        self.assertIs(report["privacy"]["network_requests_performed"], False)
        self.assertIs(report["privacy"]["sensitive_identifiers_included"], False)

        forbidden = {
            "serial", "serial_number", "mac", "mac_address", "uuid", "hostname",
            "username", "ip", "ip_address", "wwn", "storage_wwn",
        }
        self.assertTrue(
            forbidden.isdisjoint(nested_keys(report)),
            f"report contains a forbidden identifier field: {forbidden & nested_keys(report)}",
        )

    def test_pci_identity_matches_the_python_reference_on_the_same_sysfs(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT))
        from wsm_hwcheck.collector import collect_report  # noqa: PLC0415

        python_report = collect_report(
            "/sys", "/proc", include_runtime_diagnostics=False
        )
        python_pci = {
            device.get("identity", {}).get("local_path", "").rsplit("/", 1)[-1]: device
            for device in python_report.get("devices", [])
            if device.get("bus") == "pci"
        }

        report = self.run_report()
        self.validate_schema(report)
        pascal_pci = {
            device.get("identity", {}).get("local_path", "").rsplit("/", 1)[-1]: device
            for device in report.get("devices", [])
            if device.get("bus") == "pci"
        }
        self.assertEqual(
            set(pascal_pci),
            set(python_pci),
            "FPC and Python collectors disagree about PCI functions discovered in the same sysfs tree",
        )

        for address, pascal_device in pascal_pci.items():
            with self.subTest(pci_address=address):
                pascal_identity = pascal_device["identity"]
                python_identity = python_pci[address]["identity"]
                for field in ("vendor_id", "device_id", "subsystem_vendor_id",
                              "subsystem_device_id", "revision", "class_id", "modalias"):
                    self.assertEqual(
                        pascal_identity.get(field),
                        python_identity.get(field),
                        f"PCI {address}: field {field} differs",
                    )

    def test_output_file_is_written_only_when_explicitly_requested(self) -> None:
        output_path = self.build_dir / "explicit-report.json"
        result = subprocess.run(
            [str(self.binary), "--output", str(output_path), "--compact"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(output_path.is_file())
        report = json.loads(output_path.read_text(encoding="utf-8"))
        self.validate_schema(report)


if __name__ == "__main__":
    unittest.main()
