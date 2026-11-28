# SPDX-License-Identifier: LicenseRef-Volnist
"""Guix packages for native FPC tools must be real, build-only and owner-licensed."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_hwcheck.pas"
CORE = ROOT / "tools" / "pascal" / "wsm_hwcheck_core.pas"
CLASSIFIER = ROOT / "tools" / "pascal" / "wsm_classify.pas"
PKG = ROOT / "wsm" / "packages" / "fpc-tools.scm"
MAKE = ROOT / "tools" / "pascal" / "Makefile"


class HardwareCollectorTests(unittest.TestCase):
    def test_program_and_core_unit_are_native_pascal(self) -> None:
        source = SRC.read_text(encoding="utf-8")
        core = CORE.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^program wsm_hwcheck;")
        self.assertRegex(core, r"(?m)^unit wsm_hwcheck_core;")
        self.assertIn("{$mode objfpc}{$H+}", source)
        self.assertIn("WSM_SCHEMA_VERSION = '1.1.0'", core)

    def test_report_preserves_unknown_firmware_and_local_privacy(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        for marker in (
            "'requirement', 'unknown'", "'runtime_status', 'unknown'",
            "'redistribution_status', 'unknown'", "'strict-local'",
            "'network_upload_performed', False", "'network_requests_performed', False",
        ):
            self.assertIn(marker, core)

    def test_collector_is_read_only_and_uses_sysfs_driver_link(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        self.assertIn("fpReadLink(PChar(Path)", core)
        for forbidden in ("fpPWrite", "fpWrite(", "Rewrite(", "DeleteFile("):
            self.assertNotIn(forbidden, core)


class ClassifierTests(unittest.TestCase):
    def test_classifier_uses_fpjson_and_parses_once(self) -> None:
        source = CLASSIFIER.read_text(encoding="utf-8")
        self.assertIn("fpjson", source)
        self.assertIn("jsonparser", source)
        self.assertEqual(source.count("GetJSON(Text.Text, True)"), 1)
        self.assertNotIn("TJSONParser.Create", source)
        self.assertIn("JsonQuote", source)
        self.assertIn("CERTIFIED", source)
        self.assertIn('"counts"', source)
        self.assertIn("0,", source)

    def test_classifier_has_a_versioned_cli(self) -> None:
        source = CLASSIFIER.read_text(encoding="utf-8")
        self.assertIn("ToolVersion = '0.2.0'", source)
        self.assertIn("--version", source)
        self.assertIn("--help", source)


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PKG.read_text(encoding="utf-8")

    def test_fpc_is_a_native_build_input_not_a_runtime_dependency(self) -> None:
        self.assertIn("(native-inputs (list fpc))", self.text)
        self.assertNotIn("(propagated-inputs", self.text)
        self.assertNotIn("python-build-system", self.text)
        self.assertNotIn("python-jsonschema", self.text)

    def test_both_tools_are_exported_as_separate_guix_packages(self) -> None:
        self.assertIn("wsm-hwcheck-fpc", self.text)
        self.assertIn("wsm-classify-fpc", self.text)
        self.assertIn("(license wsm-license)", self.text)
        self.assertNotIn("license:gpl3+", self.text)

    def test_package_build_and_install_use_project_makefile(self) -> None:
        self.assertIn('"make" "-C" "tools/pascal"', self.text)
        self.assertIn("install-wsm-hwcheck", self.text)
        self.assertIn("install-wsm-classify", self.text)


class MakefileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MAKE.read_text(encoding="utf-8")

    def test_compiles_binaries_under_a_separate_build_directory(self) -> None:
        self.assertIn("BUILD_DIR ?= build", self.text)
        self.assertIn("build-wsm-hwcheck", self.text)
        self.assertIn("build-wsm-classify", self.text)

    def test_explicit_pascal_language_and_string_modes(self) -> None:
        self.assertIn("-Mobjfpc", self.text)
        self.assertIn("-Sh", self.text)

    def test_install_targets_only_write_into_a_supplied_prefix(self) -> None:
        self.assertIn("install-wsm-hwcheck", self.text)
        self.assertIn("install-wsm-classify", self.text)


if __name__ == "__main__":
    unittest.main()
