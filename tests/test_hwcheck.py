# SPDX-License-Identifier: LicenseRef-Volnist
"""Tests for the read-only WSM hardware inventory collector."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import sys
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_hwcheck.cli import main
from wsm_hwcheck.collector import collect_report
from wsm_hwcheck.diagnostics import (
    KernelLogSnapshot,
    derive_driver_facts,
    parse_firmware_log,
    parse_module_aliases,
    read_current_kernel_log,
    read_module_inventory,
)


SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"


def write(root: Path, relative: str, value: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path

def write_executable(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
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

    def test_usb_composite_parent_does_not_claim_interface_driver(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        usb = next(device for device in report["devices"] if device["device_id"] == "usb-1-1")
        self.assertEqual(usb["category"], "other")
        self.assertEqual(usb["driver"]["status"], "unknown")
        self.assertEqual(usb["functional_tests"], [])

    def test_display_and_storage_are_inventoried(self) -> None:
        report = collect_report(self.sysfs, self.proc)
        display = next(device for device in report["devices"] if device["category"] == "display")
        self.assertEqual(display["functional_tests"], [])
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

    def test_runtime_driver_and_firmware_evidence_integrates_with_schema_v1(self) -> None:
        modules_root = self.root / "modules"
        write(
            modules_root,
            "6.12.0-test/modules.alias",
            "alias pci:v00008086d00001912* i915\n",
        )
        write(
            modules_root,
            "6.12.0-test/modules.dep",
            "kernel/drivers/gpu/drm/i915/i915.ko.zst:\n",
        )
        write(modules_root, "6.12.0-test/modules.builtin", "")
        write(
            modules_root,
            "6.12.0-test/kernel/drivers/gpu/drm/i915/i915.ko.zst",
            "synthetic module artifact",
        )
        snapshot = KernelLogSnapshot(
            available=True,
            source="fixture:current-boot-kernel-log",
            lines=(
                "i915 0000:00:02.0: Direct firmware load for i915/example.bin failed with error -2",
            ),
        )

        report = collect_report(
            self.sysfs,
            self.proc,
            include_runtime_diagnostics=True,
            modules_root=modules_root,
            kernel_log_snapshot=snapshot,
        )
        gpu = next(
            device for device in report["devices"]
            if device["device_id"] == "pci-0000:00:02.0"
        )

        self.assertEqual(gpu["driver"]["status"], "bound")
        self.assertEqual(gpu["driver"]["candidate"], "i915")
        self.assertEqual(gpu["firmware"]["requirement"], "required")
        self.assertEqual(gpu["firmware"]["runtime_status"], "missing")
        self.assertIn(
            "Runtime firmware blob missing: i915/example.bin (kernel error -2).",
            gpu["firmware"]["kernel_log_evidence"],
        )
        self.assertEqual(
            {item["kind"] for item in gpu["evidence"]},
            {"live-observation", "database-record", "kernel-log"},
        )
        self.assertFalse(report["privacy"]["network_requests_performed"])
        self.assertEqual(list(self.validator().iter_errors(report)), [])

    def test_direct_loading_trace_stays_unknown_in_schema_valid_report(self) -> None:
        snapshot = KernelLogSnapshot(
            available=True,
            source="fixture:current-boot-kernel-log",
            lines=(
                "i915 0000:00:02.0: direct-loading i915/example.bin",
            ),
        )
        report = collect_report(
            self.sysfs,
            self.proc,
            include_runtime_diagnostics=True,
            modules_root=self.root / "missing-modules",
            kernel_log_snapshot=snapshot,
        )
        gpu = next(
            device for device in report["devices"]
            if device["device_id"] == "pci-0000:00:02.0"
        )

        self.assertEqual(gpu["firmware"]["requirement"], "required")
        self.assertEqual(
            gpu["firmware"]["runtime_status"],
            "available-not-confirmed-loaded",
        )
        self.assertIn(
            "final device assignment",
            gpu["firmware"]["kernel_log_evidence"][0],
        )
        kernel_evidence = next(item for item in gpu["evidence"] if item["kind"] == "kernel-log")
        self.assertEqual(kernel_evidence["confidence"], "confirmed")
        self.assertIn("remain unconfirmed", kernel_evidence["summary"])
        self.assertEqual(list(self.validator().iter_errors(report)), [])

    def test_unavailable_runtime_sources_leave_facts_unknown_or_preserved(self) -> None:
        snapshot = KernelLogSnapshot(
            available=False,
            source="current-boot kernel log",
            reason="permission-denied",
        )
        report = collect_report(
            self.sysfs,
            self.proc,
            include_runtime_diagnostics=True,
            modules_root=self.root / "missing-modules",
            kernel_log_snapshot=snapshot,
        )
        gpu = next(
            device for device in report["devices"]
            if device["device_id"] == "pci-0000:00:02.0"
        )

        self.assertEqual(gpu["driver"]["status"], "bound")
        self.assertEqual(gpu["firmware"]["requirement"], "unknown")
        self.assertEqual(gpu["firmware"]["runtime_status"], "unknown")
        diagnostic_collectors = [
            item for item in report["collectors"]
            if item["name"] in {
                "wsm-module-alias-database",
                "wsm-current-boot-kernel-log",
                "wsm-installed-module-index",
            }
        ]
        self.assertEqual(len(diagnostic_collectors), 3)
        self.assertTrue(all(not item["available"] for item in diagnostic_collectors))
        self.assertEqual(list(self.validator().iter_errors(report)), [])

    def test_cli_writes_json_to_stdout_by_default(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([
                "--sysfs-root", str(self.sysfs),
                "--proc-root", str(self.proc),
                "--no-runtime-diagnostics",
            ])
        self.assertEqual(result, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["schema_version"], "1.0.0")


class DriverAliasEvidenceTests(unittest.TestCase):
    MODALIAS = "pci:v00008086d00001912sv00001458sd0000D000bc03sc00i00"

    def test_module_alias_match_is_case_insensitive_and_deduplicated(self) -> None:
        aliases = """
# generated metadata
alias pci:v00008086d00001912* i915
alias pci:v00008086d00001912* i915
alias pci:v00008086d0000* nouveau
alias pci:v00008086d00001912* ../invalid
"""
        self.assertEqual(
            parse_module_aliases(self.MODALIAS, aliases),
            ("i915", "nouveau"),
        )

    def test_unavailable_alias_database_is_unknown_not_empty(self) -> None:
        self.assertIsNone(parse_module_aliases(self.MODALIAS, None))
        self.assertEqual(parse_module_aliases(self.MODALIAS, ""), ())

    def test_single_alias_candidate_is_available_only(self) -> None:
        facts = derive_driver_facts(
            {"status": "unknown"},
            modalias=self.MODALIAS,
            aliases_text="alias pci:v00008086d00001912* i915\n",
        )
        self.assertEqual(facts["status"], "available-only")
        self.assertEqual(facts["candidate"], "i915")
        self.assertNotIn("module_loaded", facts)

    def test_loaded_candidate_without_binding_is_not_reported_as_bound(self) -> None:
        facts = derive_driver_facts(
            {"status": "unknown"},
            modalias=self.MODALIAS,
            aliases_text="alias pci:v00008086d00001912* i915\n",
            loaded_modules={"i915"},
        )
        self.assertEqual(facts["status"], "module-loaded-unbound")
        self.assertTrue(facts["module_loaded"])
        self.assertEqual(facts["module"], "i915")

    def test_bound_driver_evidence_takes_precedence(self) -> None:
        facts = derive_driver_facts(
            {"status": "bound", "bound_driver": "i915", "module_loaded": True},
            modalias=self.MODALIAS,
            aliases_text="alias pci:v00008086d00001912* i915\n",
        )
        self.assertEqual(facts["status"], "bound")
        self.assertEqual(facts["bound_driver"], "i915")

    def test_no_alias_match_is_scoped_to_current_kernel_database(self) -> None:
        facts = derive_driver_facts(
            {"status": "unknown"},
            modalias=self.MODALIAS,
            aliases_text="alias usb:v1234p5678* example\n",
        )
        self.assertEqual(facts["status"], "none-known")
        self.assertIn("not a global incompatibility", facts["notes"])


class ModuleInventoryTests(unittest.TestCase):
    MODALIAS = "pci:v00008086d00001912sv00001458sd0000D000bc03sc00i00"

    def test_compressed_module_file_is_verified_from_modules_dep(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(
                root,
                "modules.dep",
                "kernel/drivers/gpu/drm/i915/i915.ko.zst:\n",
            )
            write(root, "modules.builtin", "")
            write(
                root,
                "kernel/drivers/gpu/drm/i915/i915.ko.zst",
                "synthetic module bytes",
            )
            inventory = read_module_inventory(root)
            facts = derive_driver_facts(
                {"status": "unknown"},
                modalias=self.MODALIAS,
                aliases_text="alias pci:v00008086d00001912* i915\n",
                module_inventory=inventory,
            )

            self.assertTrue(inventory.available)
            self.assertTrue(inventory.complete)
            self.assertIn("i915", inventory.installed_modules)
            self.assertEqual(facts["status"], "available-only")
            self.assertEqual(facts["candidate"], "i915")
            self.assertIn("present on disk", facts["notes"])

    def test_builtin_module_is_verified_from_modules_builtin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "modules.dep", "")
            write(root, "modules.builtin", "kernel/drivers/gpu/drm/i915.ko\n")
            inventory = read_module_inventory(root)
            facts = derive_driver_facts(
                {"status": "unknown"},
                modalias=self.MODALIAS,
                aliases_text="alias pci:v00008086d00001912* i915\n",
                module_inventory=inventory,
            )

            self.assertTrue(inventory.complete)
            self.assertIn("i915", inventory.built_in_modules)
            self.assertEqual(facts["status"], "available-only")
            self.assertEqual(facts["candidate"], "i915")
            self.assertIn("built into the kernel", facts["notes"])

    def test_stale_alias_without_module_artifact_is_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "modules.dep", "")
            write(root, "modules.builtin", "")
            inventory = read_module_inventory(root)
            facts = derive_driver_facts(
                {"status": "unknown"},
                modalias=self.MODALIAS,
                aliases_text="alias pci:v00008086d00001912* i915\n",
                module_inventory=inventory,
            )

            self.assertTrue(inventory.complete)
            self.assertEqual(facts["status"], "none-known")
            self.assertIn("corroborated", facts["notes"])

    def test_module_symlink_outside_kernel_tree_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "modules"
            root.mkdir()
            outside = parent / "outside.ko"
            outside.write_text("not inside module tree", encoding="utf-8")
            linked = root / "kernel/drivers/gpu/drm/i915/i915.ko"
            linked.parent.mkdir(parents=True)
            linked.symlink_to(outside)
            write(
                root,
                "modules.dep",
                "kernel/drivers/gpu/drm/i915/i915.ko:\n",
            )
            write(root, "modules.builtin", "")
            inventory = read_module_inventory(root)
            facts = derive_driver_facts(
                {"status": "unknown"},
                modalias=self.MODALIAS,
                aliases_text="alias pci:v00008086d00001912* i915\n",
                module_inventory=inventory,
            )

            self.assertTrue(inventory.complete)
            self.assertNotIn("i915", inventory.installed_modules)
            self.assertEqual(facts["status"], "none-known")

    def test_module_path_traversal_entry_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "modules.dep", "../../i915.ko:\n")
            write(root, "modules.builtin", "")
            inventory = read_module_inventory(root)

            self.assertTrue(inventory.complete)
            self.assertEqual(inventory.installed_modules, frozenset())
            self.assertEqual(inventory.built_in_modules, frozenset())

    def test_incomplete_module_indexes_do_not_create_false_negative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root, "modules.dep", "")
            inventory = read_module_inventory(root)
            facts = derive_driver_facts(
                {"status": "unknown"},
                modalias=self.MODALIAS,
                aliases_text="alias pci:v00008086d00001912* i915\n",
                module_inventory=inventory,
            )

            self.assertTrue(inventory.available)
            self.assertFalse(inventory.complete)
            self.assertEqual(facts["status"], "available-only")
            self.assertIn("incomplete", facts["notes"])


class RuntimeFirmwareEvidenceTests(unittest.TestCase):
    LOCATOR = "0000:00:14.3"

    def test_errno_enoent_means_missing_runtime_blob(self) -> None:
        result = parse_firmware_log(
            [
                "iwlwifi 0000:00:14.3: Direct firmware load for iwlwifi/test.ucode failed with error -2"
            ],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.requirement, "required")
        self.assertEqual(result.runtime_status, "missing")
        self.assertIn("iwlwifi/test.ucode", result.kernel_log_evidence[0])

    def test_non_enoent_failure_is_load_error(self) -> None:
        result = parse_firmware_log(
            [
                "device 0000:00:14.3: Direct firmware load for iwlwifi/test.ucode failed with error -13"
            ],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.runtime_status, "load-error")
        self.assertIn("error -13", result.kernel_log_evidence[0])

    def test_driver_firmware_version_is_not_device_load_confirmation(self) -> None:
        result = parse_firmware_log(
            ["iwlwifi 0000:00:14.3: loaded firmware version 89.202a2f7b.0"],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.requirement, "required")
        self.assertEqual(result.runtime_status, "available-not-confirmed-loaded")
        self.assertIn("device acceptance and initialization remain unconfirmed", result.kernel_log_evidence[0])

    def test_direct_loading_trace_is_not_mistaken_for_driver_success(self) -> None:
        result = parse_firmware_log(
            ["iwlwifi 0000:00:14.3: direct-loading iwlwifi/test.ucode"],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.requirement, "required")
        self.assertEqual(result.runtime_status, "available-not-confirmed-loaded")
        self.assertIn("final device assignment", result.kernel_log_evidence[0])

    def test_generic_firmware_loaded_text_is_not_driver_success(self) -> None:
        result = parse_firmware_log(
            ["device 0000:00:14.3: firmware loaded successfully"],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.requirement, "unknown")
        self.assertEqual(result.runtime_status, "unknown")

    def test_unrelated_device_and_prefix_similar_locator_are_ignored(self) -> None:
        result = parse_firmware_log(
            [
                "device 0000:00:14.30: Direct firmware load for wrong.bin failed with error -2",
                "device 0000:00:15.3: Direct firmware load for other.bin failed with error -2",
            ],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.runtime_status, "unknown")
        self.assertEqual(result.kernel_log_evidence, ())

    def test_no_message_is_unknown_and_not_not_needed(self) -> None:
        result = parse_firmware_log(
            ["iwlwifi 0000:00:14.3: initialized"],
            device_locator=self.LOCATOR,
        )
        self.assertEqual(result.requirement, "unknown")
        self.assertEqual(result.runtime_status, "unknown")

    def test_raw_log_line_is_not_retained_in_report_evidence(self) -> None:
        raw = (
            "device 0000:00:14.3 user=private-user@example.invalid "
            "Direct firmware load for iwlwifi/test.ucode failed with error -2"
        )
        result = parse_firmware_log([raw], device_locator=self.LOCATOR)
        self.assertNotIn(raw, " ".join(result.kernel_log_evidence))
        self.assertNotIn("private-user", " ".join(result.kernel_log_evidence))

    def test_usb_interface_locator_matches_but_not_neighbor_device(self) -> None:
        result = parse_firmware_log(
            [
                "usb 1-2:1.0: Direct firmware load for wifi/blob.bin failed with error -2",
                "usb 1-20:1.0: Direct firmware load for other/blob.bin failed with error -2",
            ],
            device_locator="1-2",
        )
        self.assertEqual(result.runtime_status, "missing")
        self.assertIn("wifi/blob.bin", result.kernel_log_evidence[0])

    def test_log_reader_falls_back_to_dmesg_with_fixed_read_only_args(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journalctl = write_executable(
                root,
                "journalctl",
                "import sys\nsys.stderr.write('Permission denied\\n')\nraise SystemExit(1)\n",
            )
            dmesg = write_executable(
                root,
                "dmesg",
                "import sys\nsys.stdout.write('line one\\nline two\\n')\n",
            )
            calls = []

            def popen_factory(command, **kwargs):
                calls.append((command, kwargs))
                return subprocess.Popen(command, **kwargs)

            result = read_current_kernel_log(
                popen_factory=popen_factory,
                which=lambda name: str(journalctl if name == "journalctl" else dmesg),
            )
            self.assertTrue(result.available)
            self.assertEqual(result.source, "dmesg current-boot kernel log")
            self.assertEqual(result.lines, ("line one", "line two"))
            self.assertEqual(calls[0][0][1:], [
                "-k", "-b", "--no-pager", "--output=cat", "--lines=4096"
            ])
            self.assertEqual(calls[1][0][1:], ["--color=never"])
            for _, kwargs in calls:
                self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
                self.assertIs(kwargs["stdout"], subprocess.PIPE)
                self.assertIs(kwargs["stderr"], subprocess.PIPE)
                self.assertTrue(kwargs["close_fds"])
                self.assertNotIn("shell", kwargs)

    def test_log_reader_bounds_streamed_output_bytes_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journalctl = write_executable(
                root,
                "journalctl",
                "for index in range(100000):\n"
                "    print(f'line-{index:06d}-' + 'x' * 64)\n",
            )
            result = read_current_kernel_log(
                which=lambda name: str(journalctl) if name == "journalctl" else None,
            )
            self.assertTrue(result.available)
            self.assertTrue(result.truncated)
            self.assertLessEqual(
                len("\n".join(result.lines).encode("utf-8")),
                2 * 1024 * 1024,
            )
            self.assertEqual(len(result.lines), 4096)
            self.assertTrue(result.lines[-1].startswith("line-099999-"))

    def test_log_reader_enforces_wall_clock_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journalctl = write_executable(
                root, "journalctl", "import time\ntime.sleep(2)\n"
            )
            dmesg = write_executable(
                root, "dmesg", "import time\ntime.sleep(2)\n"
            )
            result = read_current_kernel_log(
                which=lambda name: str(journalctl if name == "journalctl" else dmesg),
                timeout=0.05,
            )
            self.assertFalse(result.available)
            self.assertEqual(result.reason, "timeout")

    def test_log_reader_returns_bounded_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journalctl = write_executable(
                root,
                "journalctl",
                "for index in range(5000):\n    print(f'line {index}')\n",
            )
            result = read_current_kernel_log(
                which=lambda name: str(journalctl) if name == "journalctl" else None,
            )
            self.assertTrue(result.available)
            self.assertTrue(result.truncated)
            self.assertEqual(len(result.lines), 4096)
            self.assertEqual(result.lines[0], "line 904")

    def test_log_reader_reports_unavailable_without_commands(self) -> None:
        result = read_current_kernel_log(which=lambda name: None)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "not-installed")

if __name__ == "__main__":
    unittest.main()
