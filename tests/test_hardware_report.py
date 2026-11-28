# SPDX-License-Identifier: LicenseRef-Volnist
"""Validation tests for the WSM hardware evidence report contract."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.report_schema import (  # noqa: E402
    CURRENT_VERSION,
    SUPPORTED_VERSIONS,
    UnsupportedSchemaVersion,
    schema_path_for,
)

SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "hardware"


def validator_for(report: dict) -> Draft202012Validator:
    """Validate a report against the schema published for its own version."""
    with schema_path_for(report.get("schema_version")).open(encoding="utf-8") as stream:
        schema = json.load(stream)
    return Draft202012Validator(schema, format_checker=FormatChecker())


class HardwareReportSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            cls.schema = json.load(stream)
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def test_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(self.schema)

    def test_all_synthetic_fixtures_validate(self) -> None:
        fixtures = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertGreaterEqual(len(fixtures), 3, "Expected the three baseline fixtures.")

        for fixture_path in fixtures:
            with self.subTest(fixture=fixture_path.name):
                with fixture_path.open(encoding="utf-8") as stream:
                    report = json.load(stream)
                errors = sorted(
                    validator_for(report).iter_errors(report),
                    key=lambda error: list(error.absolute_path),
                )
                self.assertEqual(
                    errors,
                    [],
                    "\\n".join(
                        f"{list(error.absolute_path)}: {error.message}"
                        for error in errors
                    ),
                )

    def test_sensitive_identifiers_are_rejected(self) -> None:
        fixture_path = FIXTURE_DIR / "desktop-observed.json"
        with fixture_path.open(encoding="utf-8") as stream:
            report = json.load(stream)

        unsafe_report = copy.deepcopy(report)
        unsafe_report["devices"][0]["identity"]["serial_number"] = "DO-NOT-STORE"
        self.assertFalse(self.validator.is_valid(unsafe_report))

    def test_network_requests_are_forbidden_in_v1(self) -> None:
        fixture_path = FIXTURE_DIR / "desktop-observed.json"
        with fixture_path.open(encoding="utf-8") as stream:
            report = json.load(stream)

        unsafe_report = copy.deepcopy(report)
        unsafe_report["privacy"]["network_upload_performed"] = True
        self.assertFalse(self.validator.is_valid(unsafe_report))

        lookup_report = copy.deepcopy(report)
        lookup_report["privacy"]["network_requests_performed"] = True
        self.assertFalse(self.validator.is_valid(lookup_report))

    def test_unknown_is_not_misrepresented_as_failure(self) -> None:
        fixture_path = FIXTURE_DIR / "unknown-incomplete.json"
        with fixture_path.open(encoding="utf-8") as stream:
            report = json.load(stream)

        device = report["devices"][0]
        self.assertEqual(device["discovery_status"], "unknown")
        self.assertEqual(device["driver"]["status"], "unknown")
        self.assertEqual(device["functional_tests"][0]["status"], "not-run")


class ReportVersioningTests(unittest.TestCase):
    """1.1.0 adds optional facts; a 1.0.0 report must stay readable."""

    def load_fixture(self) -> dict:
        with (FIXTURE_DIR / "desktop-observed.json").open(encoding="utf-8") as stream:
            return json.load(stream)

    def current_schema(self) -> dict:
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            return json.load(stream)

    def test_current_schema_pins_the_current_version(self) -> None:
        schema = self.current_schema()
        self.assertEqual(CURRENT_VERSION, "1.1.0")
        self.assertEqual(schema["properties"]["schema_version"]["const"], CURRENT_VERSION)
        self.assertEqual(SUPPORTED_VERSIONS, ("1.0.0", CURRENT_VERSION))

    def test_frozen_1_0_0_schema_keeps_old_reports_valid(self) -> None:
        report = self.load_fixture()
        self.assertEqual(report["schema_version"], "1.0.0")
        self.assertEqual(list(validator_for(report).iter_errors(report)), [])

        # The boundary is explicit, not silent: the 1.1.0 file pins its own
        # version, so a 1.0.0 report is validated with the frozen 1.0.0 file.
        current = Draft202012Validator(self.current_schema(), format_checker=FormatChecker())
        self.assertTrue(list(current.iter_errors(report)))

    def test_unsupported_version_is_refused(self) -> None:
        for version in ("9.9.9", "1.0", "", None):
            with self.subTest(version=version):
                with self.assertRaises(UnsupportedSchemaVersion):
                    schema_path_for(version)

    def test_device_fact_objects_validate(self) -> None:
        report = self.load_fixture()
        report["schema_version"] = CURRENT_VERSION
        report["environment"]["boot_mode_evidence"] = (
            "sysfs:/firmware/efi is present: the kernel was booted through EFI."
        )
        report["environment"].setdefault("platform", {})["bios_release"] = "5.12"
        device = report["devices"][0]
        device["cpu"] = {
            "family": "6",
            "model_number": "94",
            "stepping": "3",
            "microcode": "0xf0",
            "logical_processors": 4,
        }
        device["gpu"] = {
            "boot_vga": True,
            "drm_cards": ["card0"],
            "pci_link": {
                "current_speed": "8.0 GT/s PCIe",
                "current_width": 16,
                "max_speed": "8.0 GT/s PCIe",
                "max_width": 16,
            },
        }
        device["network"] = {
            "status": "observed",
            "interfaces": [
                {
                    "name": "enp3s0",
                    "operstate": "up",
                    "carrier": True,
                    "speed_mbps": 1000,
                    "duplex": "full",
                    "mtu": 1500,
                }
            ],
        }
        device["storage"] = {
            "capacity_bytes": 1000204886016,
            "logical_block_size": 512,
            "physical_block_size": 4096,
            "rotational": False,
            "removable": False,
            "read_only": False,
            "transport": "nvme",
            "partitions": [
                {"name": "nvme0n1p1", "number": 1, "start_sector": 2048, "sectors": 1000202752}
            ],
        }
        errors = list(validator_for(report).iter_errors(report))
        self.assertEqual(
            errors,
            [],
            "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors),
        )

    def test_unreadable_facts_are_listed_not_filled_in(self) -> None:
        report = self.load_fixture()
        report["schema_version"] = CURRENT_VERSION
        storage = {
            "unavailable": ["capacity_bytes", "transport"],
            "partitions": [],
        }
        report["devices"][0]["storage"] = storage
        self.assertEqual(list(validator_for(report).iter_errors(report)), [])

        guessed = copy.deepcopy(report)
        guessed["devices"][0]["storage"]["capacity_bytes"] = "about one terabyte"
        self.assertTrue(list(validator_for(guessed).iter_errors(guessed)))

    def test_unknown_boot_mode_remains_allowed(self) -> None:
        report = self.load_fixture()
        report["schema_version"] = CURRENT_VERSION
        report["environment"]["boot_mode"] = "unknown"
        report["environment"]["boot_mode_evidence"] = "no readable source"
        self.assertEqual(list(validator_for(report).iter_errors(report)), [])


if __name__ == "__main__":
    unittest.main()
