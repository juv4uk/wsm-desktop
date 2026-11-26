# SPDX-License-Identifier: LicenseRef-Volnist
"""Validation tests for the WSM hardware evidence report contract."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "hardware"


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
                    self.validator.iter_errors(report),
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


if __name__ == "__main__":
    unittest.main()
