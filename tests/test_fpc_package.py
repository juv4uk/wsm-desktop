# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC packages must compile, obey the schemas and match Python evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
PASCAL_DIR = ROOT / "tools" / "pascal"
HW_SOURCE = PASCAL_DIR / "wsm_hwcheck.pas"
CLASSIFY_SOURCE = PASCAL_DIR / "wsm_classify.pas"
PKG = ROOT / "wsm" / "packages" / "fpc-tools.scm"
LICENSES = ROOT / "wsm" / "licenses.scm"
MAKE = PASCAL_DIR / "Makefile"
FPC_WORKFLOW = ROOT / ".github" / "workflows" / "fpc-build.yml"
REPORT_SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"
CLASSIFICATION_SCHEMA = ROOT / "schemas" / "hardware-classification.schema.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validate_document(path: Path, payload: dict) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        raise AssertionError(
            "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors)
        )


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = HW_SOURCE.read_text(encoding="utf-8")

    def test_it_is_a_program_and_pins_the_current_report_schema(self) -> None:
        self.assertRegex(self.text, r"(?m)^program wsm_hwcheck;")
        self.assertIn("SchemaVersion = '1.1.0'", self.text)

    def test_pci_sysfs_symlinks_are_included(self) -> None:
        self.assertIn("faAnyFile or faSymLink", self.text)
        self.assertIn("DirectoryExists(DevicePath)", self.text)

    def test_pci_categories_match_the_python_collector(self) -> None:
        for category in (
            "Result := 'gpu'",
            "Result := 'network'",
            "Result := 'audio'",
            "Result := 'storage-controller'",
            "Result := 'usb-controller'",
            "Result := 'other'",
        ):
            with self.subTest(category=category):
                self.assertIn(category, self.text)

    def test_driver_binding_and_module_presence_are_distinguished(self) -> None:
        self.assertIn("DriverLink(DevicePath, '/driver')", self.text)
        self.assertIn("DriverLink(DevicePath, '/driver/module')", self.text)
        self.assertIn("bound_driver", self.text)
        self.assertIn("'none-known'", self.text)
        self.assertIn("module_loaded", self.text)

    def test_report_envelope_and_device_required_fields_are_present(self) -> None:
        for field in (
            "schema_version", "report_id", "collected_at", "environment",
            "collectors", "devices", "privacy", "boot_mode_evidence",
            "discovery_status", "driver", "firmware", "functional_tests",
            "evidence", "redistribution_status", "network_requests_performed",
        ):
            with self.subTest(field=field):
                self.assertIn("'" + field + "'", self.text)

    def test_report_uses_kernel_identity_and_utc_timestamp(self) -> None:
        self.assertIn("fpUname(SystemName)", self.text)
        self.assertIn("DateTimeToUnix(Now, False)", self.text)
        self.assertIn("FormatDateTime(", self.text)
        self.assertIn("UnixToDateTime(Epoch, True)", self.text)
        self.assertIn('T"hh":"nn":"ss"Z"', self.text)

    def test_pci_results_are_sorted_and_sensitive_identifiers_are_not_added(self) -> None:
        self.assertIn("SortDevices(Devices)", self.text)
        for forbidden in ("product_uuid", "board_serial", "chassis_serial", "serial_number", "macaddress"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_it_has_no_write_or_execution_path(self) -> None:
        for forbidden in ("fpWrite", "Rewrite(", "fpExec", "RunCommand", "TProcess"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_an_empty_report_is_still_json_and_returns_a_diagnostic_code(self) -> None:
        self.assertIn("No readable PCI functions were found", self.text)
        self.assertIn("Halt(4)", self.text)


class ClassifierSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CLASSIFY_SOURCE.read_text(encoding="utf-8")

    def test_parser_is_consumed_once_and_uses_structured_json_output(self) -> None:
        self.assertIn("RootData := GetJSON(InputText.Text)", self.text)
        self.assertIn("TJSONObject.Create", self.text)
        self.assertNotIn("Parser.Parse", self.text)

    def test_it_emits_the_complete_classification_contract(self) -> None:
        for field in (
            "decision_policy", "coverage", "devices", "reasons",
            "observation", "evidence_states", "functional_tests", "device_evidence",
            "certified", "known", "unknown",
        ):
            with self.subTest(field=field):
                self.assertIn("'" + field + "'", self.text)

    def test_only_explicit_failed_status_blocks_known(self) -> None:
        self.assertIn("Str(TJSONObject(ItemData), 'status') = 'failed'", self.text)
        self.assertIn("'driver-bound-not-tested'", self.text)
        self.assertIn("'candidate-only'", self.text)
        self.assertNotIn("'supported-tested') then", self.text)

    def test_json_output_is_built_from_fpjson_not_manual_interpolation(self) -> None:
        self.assertIn("fpjson", self.text)
        self.assertIn("Result.Add('subsystems', SubsystemArray)", self.text)
        self.assertNotIn("Ids := Ids +", self.text)
        self.assertNotIn("Write('", self.text)

    def test_certification_is_never_claimed(self) -> None:
        self.assertIn("Counts.Add('certified', 0)", self.text)
        self.assertNotIn("LevelCertified", self.text)


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PKG.read_text(encoding="utf-8")
        self.license_text = LICENSES.read_text(encoding="utf-8")

    def test_all_native_packages_use_fpc_as_a_build_time_input(self) -> None:
        self.assertIn("(gnu packages pascal)", self.text)
        self.assertEqual(self.text.count("(define-public wsm-"), 6)
        self.assertEqual(self.text.count("(native-inputs (list fpc))"), 2)
        self.assertEqual(self.text.count("(define (fpc-package-arguments"), 1)
        self.assertNotIn("(inherit wsm-hwcheck-fpc)", self.text)
        self.assertIn("(define (make-fpc-reader", self.text)
        self.assertIn("(define (fpc-installer-arguments)", self.text)
        self.assertIn("(inputs (list wsm-preflight-fpc", self.text)
        self.assertIn("(symlink (string-append input \"/bin/\" program)", self.text)
        for name in ("wsm-hwcheck-fpc", "wsm-classify-fpc", "wsm-partition-fpc", "wsm-profile-fpc", "wsm-preflight-fpc", "wsm-install-fpc"):
            self.assertIn(name, self.text)

    def test_package_license_is_the_actual_owner_license(self) -> None:
        self.assertIn("(license wsm-license)", self.text)
        self.assertIn("(wsm licenses)", self.text)
        self.assertNotIn("license:gpl3+", self.text)
        self.assertIn('file://LICENSE', self.license_text)
        self.assertIn("LicenseRef-Volnist", self.license_text)

    def test_guix_builds_from_the_pascal_directory_and_installs_exact_outputs(self) -> None:
        self.assertIn('"make" "-C" "tools/pascal"', self.text)
        self.assertIn("tools/pascal/build/", self.text)
        self.assertIn('file-append fpc "/bin/fpc"', self.text)

    def test_fpc_is_not_a_runtime_or_propagated_dependency(self) -> None:
        self.assertNotIn("propagated-inputs", self.text)
        self.assertNotIn("python-build-system", self.text)
        self.assertNotIn("propagated-inputs", self.text)
        self.assertNotIn("(gnu packages python", self.text)


class MakefileAndWorkflowTests(unittest.TestCase):
    def test_makefile_outputs_correct_names_outside_the_source_directory(self) -> None:
        text = MAKE.read_text(encoding="utf-8")
        self.assertIn("BUILD_DIR ?= build", text)
        for name in ("wsm-hwcheck", "wsm-classify", "wsm-partition", "wsm-profile", "wsm-preflight", "wsm-install"):
            self.assertIn(f"-o$(BUILD_DIR)/{name}", text)
        self.assertIn("-Mobjfpc", text)
        self.assertIn("-Sh", text)
        self.assertIn("rm -rf $(BUILD_DIR)", text)
        self.assertNotIn("-owsw-", text)

    def test_fpc_ci_builds_pas_files_and_executes_runtime_parity(self) -> None:
        text = FPC_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("fp-compiler-3.2.2", text)
        self.assertIn("fp-units-fcl-3.2.2", text)
        self.assertIn("make -C tools/pascal clean all", text)
        self.assertIn("python3 tests/test_fpc_package.py", text)
        self.assertIn("tests/test_fpc_partition.py", text)
        self.assertIn("python3 tests/test_fpc_partition.py", text)
        self.assertIn("python3 tests/test_fpc_profile.py", text)
        self.assertIn("python3 tests/test_fpc_preflight.py", text)
        self.assertIn("python3 tests/test_fpc_cli.py", text)
        self.assertIn("jsonschema[format]==4.26.0", text)
        self.assertNotIn("git ls-files '*.lpr'", text)


@unittest.skipUnless(shutil.which("fpc"), "FPC is not installed; compiler/runtime parity is not proven locally")
class RuntimeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-parity-")
        cls.build_dir = Path(cls.temporary.name) / "build"
        completed = subprocess.run(
            [
                "make", "-C", str(PASCAL_DIR),
                f"BUILD_DIR={cls.build_dir}",
                "all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "FPC Makefile build failed.\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        cls.hwcheck = cls.build_dir / "wsm-hwcheck"
        cls.classifier = cls.build_dir / "wsm-classify"
        cls.partition = cls.build_dir / "wsm-partition"
        cls.profile = cls.build_dir / "wsm-profile"
        cls.preflight = cls.build_dir / "wsm-preflight"
        cls.installer = cls.build_dir / "wsm-install"
        if not all(path.is_file() for path in (
            cls.hwcheck, cls.classifier, cls.partition, cls.profile, cls.preflight, cls.installer
        )):
            raise AssertionError("FPC Makefile did not produce all six expected binaries")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_hardware_reader_emits_a_schema_valid_pci_subset_with_python_parity(self) -> None:
        from wsm_hwcheck.collector import collect_report

        completed = subprocess.run(
            [str(self.hwcheck)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn(completed.returncode, (0, 3, 4), completed.stderr)
        payload = json.loads(completed.stdout)
        validate_document(REPORT_SCHEMA, payload)

        python_report = collect_report(include_runtime_diagnostics=False)
        for field in ("architecture", "kernel_release", "boot_mode", "virtualization"):
            self.assertEqual(
                payload["environment"].get(field),
                python_report["environment"].get(field),
                f"environment.{field} disagrees with the Python reference",
            )

        python_pci = {
            item["device_id"]: item
            for item in python_report["devices"]
            if item.get("bus") == "pci"
        }
        pascal_pci = {
            item["device_id"]: item
            for item in payload["devices"]
            if item.get("bus") == "pci"
        }
        self.assertEqual(set(pascal_pci), set(python_pci))
        self.assertEqual(list(pascal_pci), sorted(pascal_pci))

        identity_fields = (
            "vendor_id", "device_id", "subsystem_vendor_id",
            "subsystem_device_id", "revision", "class_id", "modalias", "local_path",
        )
        driver_fields = ("status", "bound_driver", "module", "module_loaded", "notes")
        for device_id, pascal_device in pascal_pci.items():
            python_device = python_pci[device_id]
            self.assertEqual(pascal_device["category"], python_device["category"])
            for field in identity_fields:
                self.assertEqual(
                    pascal_device.get("identity", {}).get(field),
                    python_device.get("identity", {}).get(field),
                    f"{device_id}: identity.{field} differs",
                )
            for field in driver_fields:
                self.assertEqual(
                    pascal_device.get("driver", {}).get(field),
                    python_device.get("driver", {}).get(field),
                    f"{device_id}: driver.{field} differs",
                )

    def test_classifier_matches_the_python_contract_and_its_schema(self) -> None:
        from wsm_hwcheck.collector import collect_report
        from wsm_install.classification import classify

        report = collect_report(include_runtime_diagnostics=False)
        report_path = Path(self.temporary.name) / "hardware-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [str(self.classifier), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        validate_document(CLASSIFICATION_SCHEMA, payload)
        self.assertEqual(payload, classify(report))

    def test_classifier_matches_python_for_boundary_evidence_states(self) -> None:
        from wsm_install.classification import classify

        report = {
            "devices": [
                {
                    "device_id": "gpu-bound-built-in",
                    "category": "gpu",
                    "discovery_status": "discovered",
                    "driver": {"status": "bound", "bound_driver": "nouveau"},
                    "functional_tests": [
                        {"capability": "display-mode", "status": "passed"},
                    ],
                    "firmware": {"requirement": "unknown", "runtime_status": "unknown"},
                    "evidence": [],
                },
                {
                    "device_id": "gpu-failed-render",
                    "category": "gpu",
                    "discovery_status": "discovered",
                    "driver": {"status": "available-only", "candidate": "nouveau"},
                    "functional_tests": [
                        {"capability": "gpu-render", "status": "failed"},
                    ],
                    "firmware": {"requirement": "unknown", "runtime_status": "unknown"},
                    "evidence": [],
                },
                {
                    "device_id": "wifi-module-unbound",
                    "category": "network",
                    "discovery_status": "discovered",
                    "driver": {
                        "status": "module-loaded-unbound",
                        "module": "iwlwifi",
                        "module_loaded": True,
                    },
                    "functional_tests": [],
                    "firmware": {"requirement": "unknown", "runtime_status": "unknown"},
                    "evidence": [],
                },
                {
                    "device_id": "unknown-device",
                    "category": "other",
                    "discovery_status": "unknown",
                    "driver": None,
                    "functional_tests": [],
                    "firmware": {"requirement": "unknown", "runtime_status": "unknown"},
                    "evidence": [],
                },
            ]
        }
        report_path = Path(self.temporary.name) / "classification-boundaries.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        completed = subprocess.run(
            [str(self.classifier), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        validate_document(CLASSIFICATION_SCHEMA, payload)
        self.assertEqual(payload, classify(report))

    def test_classifier_refuses_malformed_json(self) -> None:
        report_path = Path(self.temporary.name) / "malformed.json"
        report_path.write_text("{not-json", encoding="utf-8")
        completed = subprocess.run(
            [str(self.classifier), str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 4)
        self.assertIn("not valid JSON", completed.stderr)


if __name__ == "__main__":
    unittest.main()
