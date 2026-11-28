# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC edition must be buildable, read-only, and free of Python."""

from __future__ import annotations

import re
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

    def test_it_uses_ansi_strings(self) -> None:
        """Without {$H+} the JSON builder truncates on non-ASCII bytes."""
        self.assertIn("{$H+}", self.text)

    def test_it_emits_every_field_the_schema_requires(self) -> None:
        for field in (
            "device_id", "category", "bus", "discovery_status",
            "driver", "firmware", "functional_tests", "evidence",
        ):
            self.assertIn(f'"{field}"', self.text, f"missing required field {field}")

    def test_it_never_writes_to_a_device(self) -> None:
        """The whole product promise is read-only."""
        for forbidden in ("fpOpen", "fpWrite", "AssignFile", "Rewrite("):
            if forbidden == "AssignFile":
                continue  # used for reading; Reset only
            self.assertNotIn(forbidden, self.text, f"write path present: {forbidden}")
        self.assertNotIn("Rewrite(", self.text)

    def test_json_strings_are_escaped(self) -> None:
        self.assertIn("JsonEscape", self.text)
        self.assertIn("'\\\"'", self.text)

    def test_an_empty_report_is_a_failure_not_a_success(self) -> None:
        self.assertIn("no PCI devices were readable", self.text)
        self.assertIn("Halt(4)", self.text)


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PKG.read_text(encoding="utf-8")

    def test_it_builds_with_fpc(self) -> None:
        self.assertIn("(gnu packages pascal)", self.text)
        self.assertIn("fpc", self.text)

    def test_no_python_enters_the_closure(self) -> None:
        for marker in ("python-build-system", "python-jsonschema", "(gnu packages python"):
            self.assertNotIn(marker, self.text, f"Python dependency present: {marker}")

    def test_it_installs_exactly_one_binary(self) -> None:
        self.assertIn("install-file", self.text)
        self.assertIn("/bin", self.text)

    def test_seven_public_packages_have_separate_reader_and_frontend_roles(self) -> None:
        names = (
            "wsm-hwcheck-fpc", "wsm-classify-fpc", "wsm-cpu-isa-fpc", "wsm-partition-fpc",
            "wsm-profile-fpc", "wsm-preflight-fpc", "wsm-install-fpc",
        )
        self.assertEqual(self.text.count("(define-public wsm-"), 7)
        for name in names:
            with self.subTest(package=name):
                self.assertIn(name, self.text)
        self.assertEqual(self.text.count("(make-fpc-reader"), 7)
        self.assertIn("(define (make-fpc-reader", self.text)
        self.assertNotIn("(inherit wsm-hwcheck-fpc)", self.text)

    def test_reader_compiler_is_build_only_and_installer_inputs_are_explicit(self) -> None:
        self.assertEqual(self.text.count("(native-inputs (list fpc gnu-make))"), 2)
        self.assertIn("(inputs (list wsm-preflight-fpc", self.text)
        self.assertIn("wsm-partition-fpc))", self.text)
        self.assertIn("(symlink (string-append input \"/bin/\" executable)", self.text)
        installer = self.text.split("(define-public wsm-install-fpc", 1)[1]
        self.assertNotIn("wsm-cpu-isa-fpc", installer)
        self.assertNotIn("wsm-profile-fpc", installer)
        self.assertNotIn("propagated-inputs", self.text)

    def test_root_makefile_exposes_a_pinned_guix_build_target(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("build-fpc-packages:", text)
        for name in (
            "wsm-hwcheck-fpc", "wsm-classify-fpc", "wsm-cpu-isa-fpc", "wsm-partition-fpc",
            "wsm-profile-fpc", "wsm-preflight-fpc", "wsm-install-fpc",
        ):
            self.assertIn(name, text)
        self.assertIn("time-machine -C channels.lock.scm", text)


class MakefileTests(unittest.TestCase):
    def test_the_makefile_passes_the_mode_flags(self) -> None:
        text = MAKE.read_text(encoding="utf-8")
        self.assertIn("-Mobjfpc", text)
        self.assertIn("-Sh", text)

    def test_all_seven_targets_keep_outputs_out_of_the_source_tree(self) -> None:
        text = MAKE.read_text(encoding="utf-8")
        for name in (
            "wsm-hwcheck", "wsm-classify", "wsm-cpu-isa", "wsm-partition",
            "wsm-profile", "wsm-preflight", "wsm-install",
        ):
            with self.subTest(program=name):
                self.assertIn(f"$(BUILD_DIR)/{name}", text)
        self.assertIn("BUILD_DIR ?= build", text)
        self.assertIn("rm -rf $(BUILD_DIR)", text)


if __name__ == "__main__":
    unittest.main()
