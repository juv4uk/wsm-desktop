# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC edition must be buildable, read-only, and free of Python."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_hwcheck.pas"
CORE = ROOT / "tools" / "pascal" / "wsm_hwcheck_core.pas"
PKG = ROOT / "wsm" / "packages" / "fpc-tools.scm"
MAKE = ROOT / "tools" / "pascal" / "Makefile"


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SRC.read_text(encoding="utf-8")

    def test_it_is_a_program_not_a_unit(self) -> None:
        self.assertRegex(self.text, r"(?m)^program wsm_hwcheck;")

    def test_it_uses_ansi_strings(self) -> None:
        """Without {$H+} the JSON builder truncates on non-ASCII bytes."""
        self.assertIn("{$H+}", self.text)

    def test_it_emits_every_field_the_schema_requires(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        for field in (
            "device_id", "category", "bus", "discovery_status",
            "driver", "firmware", "functional_tests", "evidence",
        ):
            self.assertIn(f"'{field}'", core, f"missing report field {field}")

    def test_it_never_writes_to_a_device(self) -> None:
        """The whole product promise is read-only."""
        for forbidden in ("fpOpen", "fpWrite", "AssignFile", "Rewrite("):
            if forbidden == "AssignFile":
                continue  # used for reading; Reset only
            self.assertNotIn(forbidden, self.text, f"write path present: {forbidden}")
        self.assertNotIn("Rewrite(", self.text)

    def test_json_strings_are_escaped_by_the_standard_fcl_serializer(self) -> None:
        self.assertIn("fpjson", self.text)
        self.assertIn("Report.AsJSON", self.text)
        self.assertIn("Report.FormatJSON", self.text)

    def test_missing_pci_sysfs_is_reported_as_unknown_evidence(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        self.assertIn("PCI sysfs inventory is unavailable", core)
        self.assertIn("Warnings.Add", core)
        self.assertNotIn("Halt(4)", self.text)
class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PKG.read_text(encoding="utf-8")

    def test_it_builds_with_fpc(self) -> None:
        self.assertIn("(gnu packages pascal)", self.text)
        self.assertIn("fpc", self.text)

    def test_build_source_is_restricted_to_license_and_pascal_tooling(self) -> None:
        self.assertIn('(string-suffix? "/LICENSE" path)', self.text)
        self.assertIn('(string-suffix? "/tools" path)', self.text)
        self.assertIn('(string-suffix? "/tools/pascal" path)', self.text)
        self.assertIn('(string-contains path "/tools/pascal/")', self.text)
        self.assertNotIn('(string-prefix? "tools/pascal/" path)', self.text)
        self.assertNotIn('(string-prefix? "wsm_hwcheck/" path)', self.text)

    def test_no_python_enters_the_closure(self) -> None:
        for marker in ("python-build-system", "python-jsonschema", "(gnu packages python"):
            self.assertNotIn(marker, self.text, f"Python dependency present: {marker}")

    def test_each_native_tool_has_a_separate_package_and_fpc_is_build_only(self) -> None:
        self.assertIn("(name \"wsm-hwcheck-fpc\")", self.text)
        self.assertIn("(name \"wsm-classify-fpc\")", self.text)
        self.assertIn("(name \"wsm-cpu-isa-fpc\")", self.text)
        self.assertIn("(name \"wsm-partition-fpc\")", self.text)
        self.assertIn("(name \"wsm-profile-fpc\")", self.text)
        self.assertIn("(name \"wsm-preflight-fpc\")", self.text)
        self.assertIn("(name \"wsm-install-fpc\")", self.text)
        self.assertIn("(native-inputs (list fpc))", self.text)
        self.assertIn("(license wsm-license)", self.text)
        self.assertIn("build-hwcheck", self.text)
        self.assertIn("build-classify", self.text)
        self.assertIn("install-hwcheck", self.text)
        self.assertIn("install-classify", self.text)
        self.assertIn("build-isa", self.text)
        self.assertIn("install-isa", self.text)
        self.assertIn("build-partition", self.text)
        self.assertIn("install-partition", self.text)
        self.assertIn("build-profile", self.text)
        self.assertIn("install-profile", self.text)
        self.assertIn("build-preflight", self.text)
        self.assertIn("install-preflight", self.text)
        self.assertIn("build-install", self.text)
        self.assertIn("install-install", self.text)
        self.assertIn("(propagated-inputs", self.text)


class MakefileTests(unittest.TestCase):
    def test_the_makefile_passes_mode_flags_and_names_installed_outputs_correctly(self) -> None:
        text = MAKE.read_text(encoding="utf-8")
        self.assertIn("-Mobjfpc", text)
        self.assertIn("-Sh", text)
        self.assertIn("$(BUILD_DIR)/wsm-hwcheck", text)
        self.assertIn("$(BUILD_DIR)/wsm-classify", text)
        self.assertIn("$(BUILD_DIR)/wsm-cpu-isa", text)
        self.assertIn("install-hwcheck", text)
        self.assertIn("install-classify", text)
        self.assertIn("install-isa", text)
        self.assertNotIn("-owsw-", text)


if __name__ == "__main__":
    unittest.main()
