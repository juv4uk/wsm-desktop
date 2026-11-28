# SPDX-License-Identifier: LicenseRef-Volnist
"""Static package-contract tests for the native FPC hardware reader."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_hwcheck.pas"
PKG = ROOT / "wsm" / "packages" / "fpc-tools.scm"
MAKE = ROOT / "tools" / "pascal" / "Makefile"


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SRC.read_text(encoding="utf-8")

    def test_it_is_a_program_not_a_unit(self) -> None:
        self.assertRegex(self.text, r"(?m)^program wsm_hwcheck;")

    def test_it_uses_long_utf8_safe_strings(self) -> None:
        self.assertIn("{$H+}", self.text)

    def test_it_targets_the_current_report_schema(self) -> None:
        self.assertIn("SchemaVersion = '1.1.0'", self.text)
        for field in (
            '"report_id"', '"collected_at"', '"environment"',
            '"collectors"', '"devices"', '"privacy"',
            '"requirement":"unknown"', '"runtime_status":"unknown"',
            '"kind":"live-observation"', '"observed_at"',
        ):
            self.assertIn(field, self.text, f"missing report field {field}")

    def test_it_never_opens_a_write_path(self) -> None:
        for forbidden in ("fpOpen(", "fpWrite(", "Rewrite(", "DeleteFile(", "RenameFile("):
            self.assertNotIn(forbidden, self.text, f"write path present: {forbidden}")
        self.assertNotIn("fpPWrite(", self.text)

    def test_json_escaping_handles_quotes_and_backslashes(self) -> None:
        self.assertIn("JsonEscape", self.text)
        self.assertIn("Result := Result + '\\' + '\"';", self.text)
        self.assertIn("Result := Result + '\\\\';", self.text)


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PKG.read_text(encoding="utf-8")

    def test_fpc_is_a_native_build_input_only(self) -> None:
        self.assertIn("(native-inputs (list fpc))", self.text)
        self.assertIn("(gnu packages pascal)", self.text)

    def test_wsm_license_is_not_mislabeled_as_gpl(self) -> None:
        self.assertIn("(license wsm-license)", self.text)
        self.assertNotIn("license:gpl3+", self.text)
        self.assertIn("(wsm licenses)", self.text)

    def test_python_is_not_in_the_package_definition(self) -> None:
        for marker in ("python-build-system", "python-jsonschema", "(gnu packages python"):
            self.assertNotIn(marker, self.text, f"Python dependency present: {marker}")

    def test_the_guix_build_uses_the_tool_directory(self) -> None:
        self.assertIn('"make" "-C" "tools/pascal"', self.text)
        self.assertIn('install-file "tools/pascal/wsm-hwcheck" bin', self.text)


class MakefileTests(unittest.TestCase):
    def test_the_makefile_passes_mode_and_string_flags(self) -> None:
        text = MAKE.read_text(encoding="utf-8")
        self.assertIn("-Mobjfpc", text)
        self.assertIn("-Sh", text)


if __name__ == "__main__":
    unittest.main()
