# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC classifier must not certify what the Python one refuses to certify."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_classify.pas"
PY = ROOT / "wsm_install" / "classification.py"


class ContractParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")
        self.py = PY.read_text(encoding="utf-8")

    def test_every_subsystem_name_matches_the_python_table(self) -> None:
        names = set(re.findall(r"\(Name: '([a-z]+)'", self.pas))
        self.assertEqual(
            names,
            {"cpu", "memory", "storage", "graphics", "network", "audio",
             "bluetooth", "input", "usb", "camera", "other"},
        )

    def test_the_category_lists_match_the_python_table(self) -> None:
        self.assertIn("'gpu|display'", self.pas)
        self.assertIn("'storage-controller|storage-device'", self.pas)

    def test_certified_stays_at_zero(self) -> None:
        """A summary that could say CERTIFIED would authorise a plan it cannot support."""
        self.assertIn("Counts.Add('certified', 0)", self.pas)
        self.assertNotIn("LevelCertified", self.pas)

    def test_a_passed_test_never_promotes_a_subsystem(self) -> None:
        """Only driver-bound-not-tested and candidate-only count as known."""
        self.assertIn("'driver-bound-not-tested'", self.pas)
        self.assertIn("'candidate-only'", self.pas)
        self.assertIn("Exit('supported-tested')", self.pas)
        self.assertIn("AllGood and (not AnyFailed)", self.pas)
        self.assertNotIn("Level := 'supported-tested'", self.pas)

    def test_a_failed_function_blocks_known(self) -> None:
        self.assertIn("FailedFunctionTest", self.pas)
        self.assertIn("AnyFailed", self.pas)

    def test_built_in_drivers_are_not_false_unknowns(self) -> None:
        self.assertIn("bound_driver", self.pas)

    def test_classification_output_matches_the_versioned_schema_shape(self) -> None:
        for field in (
            "decision_policy", "coverage", "devices", "reasons",
            "observation", "evidence_states", "functional_tests", "device_evidence",
        ):
            with self.subTest(field=field):
                self.assertIn("'" + field + "'", self.pas)
        for count in ("certified", "known", "unknown"):
            with self.subTest(count=count):
                self.assertIn("Counts.Add('" + count + "'", self.pas)

    def test_json_parser_is_not_called_twice_and_status_is_authoritative(self) -> None:
        self.assertIn("RootData := GetJSON(InputText.Text)", self.pas)
        self.assertNotIn("Parser.Parse", self.pas)
        self.assertIn("Str(TJSONObject(ItemData), 'status') = 'failed'", self.pas)


class SafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_no_write_path(self) -> None:
        for forbidden in ("Rewrite(", "Append(", "fpWrite"):
            self.assertNotIn(forbidden, self.pas, f"write path present: {forbidden}")

    def test_a_malformed_report_is_rejected(self) -> None:
        self.assertIn("not valid JSON", self.pas)
        self.assertIn("Halt(4)", self.pas)

    def test_no_external_json_library(self) -> None:
        """fpjson ships with FPC; anything else re-adds the dependency."""
        self.assertIn("fpjson", self.pas)
        for marker in ("synapse", "lazjson", "superobject"):
            self.assertNotIn(marker, self.pas)

    def test_no_dead_placeholders(self) -> None:
        self.assertNotIn("placeholder", self.pas.lower())


if __name__ == "__main__":
    unittest.main()
