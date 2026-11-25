# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the read-only WSM hardware inventory collector."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_hwcheck.cli import main
from wsm_hwcheck.collector import collect_report


SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"


def write(root: Path, relative: str, value: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


class HardwareCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sysfs = self.root / "sys"
        self.proc = self.root / "proc"
        self.sysfs.mkdir()
        self.proc.mkdir()

        write(self.proc, "sys/kernel/osrelease", "6.12.0-test\n")
        write(
            self.proc,
            "cpuinfo",
            "processor : 0\nvendor_id : GenuineIntel\nmodel name : Example Intel CPU\n",
        )
        write(self.sysfs, "firmware/efi/fw_platform_size", "64\n")
        write(self.sysfs, "class/dmi/id/sys_vendor", "Example Vendor\n")
        write(self.sysfs, "class/dmi/id/product_name", "Example Desktop\n")
        write(self.sysfs, "class/dmi/id/board_vendor", "Example Board Co.\n")
        write(self.sysfs, "class/dmi/id/board_name", "Example H170 Board\n")
        write(self.sysfs, "class/dmi/id/board_version", "1.0\n")
        write(self.sysfs, "class/dmi/id/bios_vendor", "Example BIOS Vendor\n")
        write(self.sysfs, "class/dmi/id/bios_version", "F99-example\n")
        # A BIOS date in a vendor-specific form must not leak into a date-
        # formatted schema field unless it is normalized first.

        gpu = self.sysfs / "bus/pci/devices/0000:00:02.0"
        write(gpu, "vendor", "0x8086\n")
        write(gpu, "device", "0x1912\n")
        write(gpu, "subsystem_vendor", "0x1458\n")
        write(gpu, "subsystem_device", "0xd000\n")
        write(gpu, "revision", "0x07\n")
        write(gpu, "class", "0x030000\n")
        write(gpu, "modalias", "pci:v00008086d00001912\n")

        driver = self.sysfs / "bus/pci/drivers/i915"
        module = self.sysfs / "module/i915"
        driver.mkdir(parents=True)
        module.mkdir(parents=True)
        (driver / "module").symlink_to(module, target_is_directory=True)
        (gpu / "driver").symlink_to(driver, target_is_directory=True)

        usb = self.sysfs / "bus/usb/devices/1-1"
        write(usb, "idVendor", "046d\n")
        write(usb, "idProduct", "c534\n")
        write(usb, "bDeviceClass", "00\n")
        write(usb, "manufacturer", "Example Input Vendor\n")
        write(usb, "product", "Example USB Receiver\n")
        write(usb, "bcdDevice", "12.34\n")

        block = self.sysfs / "block/sda/device"
        write(block, "vendor", "EXAMPLE\n")
        write(block, "model", "Example SSD\n")

        connector = self.sysfs / "class/drm/card0-DP-1"
        write(connector, "status", "connected\n")
        write(connector, "modes", "2560x1440\n1920x1080\n")
        write(connector, "mode", "2560x1440\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validator(self) -> Draft202012Validator:
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            schema = json.load(stream)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema, format_checker=FormatChecker())

    def test_collected_report_matches_schema(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        errors = list(self.validator().iter_errors(report))
        self.assertEqual(
            errors,
            [],
            "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors),
        )

    def test_inventory_separates_driver_binding_and_functional_tests(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        gpu = next(device for device in report["devices"] if device["device_id"] == "pci-0000:00:02.0")
        self.assertEqual(gpu["category"], "gpu")
        self.assertEqual(gpu["driver"]["status"], "bound")
        self.assertEqual(gpu["driver"]["bound_driver"], "i915")
        self.assertTrue(gpu["driver"]["module_loaded"])
        self.assertEqual(gpu["firmware"]["runtime_status"], "unknown")
        self.assertEqual(gpu["functional_tests"], [])

    def test_display_and_storage_are_inventoried(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        display = next(device for device in report["devices"] if device["category"] == "display")
        self.assertEqual(display["display"]["connector"], "card0-DP-1")
        self.assertTrue(display["display"]["connected"])
        self.assertIn("2560x1440", display["display"]["advertised_modes"])

        storage = next(device for device in report["devices"] if device["device_id"] == "block-sda")
        self.assertEqual(storage["category"], "storage-device")
        self.assertEqual(storage["identity"]["model"], "Example SSD")

    def test_report_is_local_and_does_not_include_sensitive_identifiers(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        self.assertFalse(report["privacy"]["network_upload_performed"])
        self.assertFalse(report["privacy"]["network_requests_performed"])
        self.assertFalse(report["privacy"]["sensitive_identifiers_included"])

        forbidden_keys = {
            "serial", "serial_number", "mac", "mac_address",
            "uuid", "hostname", "username", "ip_address", "wwn",
        }

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key.lower(), forbidden_keys)
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(report)

    def test_missing_sysfs_information_is_unknown_not_failure(self) -> None:
        empty_sysfs = self.root / "empty-sys"
        empty_proc = self.root / "empty-proc"
        empty_sysfs.mkdir()
        empty_proc.mkdir()
        report = collect_report(empty_sysfs, empty_proc)
        self.assertEqual(report["environment"]["boot_mode"], "unknown")
        self.assertEqual(report["devices"], [])
        self.assertFalse(report["privacy"]["network_requests_performed"])
        self.assertEqual(list(self.validator().iter_errors(report)), [])

    def test_cli_writes_json_to_stdout_by_default(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--sysfs-root", str(self.sysfs),
                "--proc-root", str(self.proc),
            ])
        self.assertEqual(result, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["schema_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
