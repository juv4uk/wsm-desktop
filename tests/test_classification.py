# SPDX-License-Identifier: LicenseRef-Volnist
"""Regression tests for conservative, evidence-bound hardware classification."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from wsm_install.classification import (  # noqa: E402
    CERTIFIED,
    DECISION_NOT_EVALUATED,
    KNOWN,
    UNKNOWN,
    ClassificationEvidenceError,
    ValidatedProfileEvidence,
    classify,
    classify_subsystem,
    evidence_state_for,
    explain,
    load_validated_profile_evidence,
)

REPORT_PATH = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"
FUNCTIONAL_BYTES = b"synthetic functional test output\n"
PROFILE_BYTES = b";; synthetic profile source\n"


def valid_report() -> dict:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    return report


def one_gpu_report() -> tuple[dict, bytes]:
    report = valid_report()
    report["devices"] = [copy.deepcopy(report["devices"][0])]
    raw = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    ).validate(json.loads(raw))
    return report, raw


def make_profile_bundle(root: Path, report: dict, report_bytes: bytes) -> Path:
    profile_root = root / "profiles" / "hardware" / "example" / "desktop"
    artifacts = profile_root / "artifacts"
    artifacts.mkdir(parents=True)
    (profile_root / "profile.scm").write_bytes(PROFILE_BYTES)
    (artifacts / "functional-test.log").write_bytes(FUNCTIONAL_BYTES)
    (artifacts / "wsm-hwcheck-report.json").write_bytes(report_bytes)

    document = {
        "schema": "wsm-profile-evidence/2",
        "profile": {
            "vendor": "Example Vendor",
            "model": "Example Desktop",
            "slug": "example/desktop",
        },
        "report_id": report["report_id"],
        "report_schema_version": report["schema_version"],
        "isa_level": "x86-64-v3",
        "verified_on": "2026-11-26",
        "verified_by": "web agent",
        "verified_functions": [
            {
                "name": "graphics",
                "status": "pass",
                "note": "synthetic test fixture only",
                "evidence": ["artifacts/functional-test.log"],
            }
        ],
        "known_limitations": [],
        "not_assessed": ["suspend/resume"],
        "profile_source": {
            "path": "profile.scm",
            "sha256": hashlib.sha256(PROFILE_BYTES).hexdigest(),
        },
        "artifacts": [
            {
                "kind": "functional-test-log",
                "path": "artifacts/functional-test.log",
                "sha256": hashlib.sha256(FUNCTIONAL_BYTES).hexdigest(),
            },
            {
                "kind": "wsm-hwcheck-report",
                "path": "artifacts/wsm-hwcheck-report.json",
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
            },
        ],
    }
    evidence_path = profile_root / "evidence.json"
    evidence_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence_path


class DriverEvidenceTests(unittest.TestCase):
    def test_real_report_driver_contract_maps_bound_driver_to_known(self) -> None:
        report = valid_report()
        gpu = report["devices"][0]
        self.assertEqual(gpu["driver"]["status"], "bound")
        self.assertEqual(gpu["driver"]["bound_driver"], "nvidia")
        self.assertEqual(evidence_state_for(gpu), "driver-bound-not-tested")

    def test_builtin_driver_is_bound_without_module_link(self) -> None:
        gpu = copy.deepcopy(valid_report()["devices"][0])
        gpu["driver"] = {"status": "bound", "bound_driver": "builtin_example"}
        self.assertEqual(evidence_state_for(gpu), "driver-bound-not-tested")

    def test_module_loaded_unbound_does_not_mean_known(self) -> None:
        gpu = copy.deepcopy(valid_report()["devices"][0])
        gpu["driver"] = {
            "status": "module-loaded-unbound",
            "module": "example",
            "module_loaded": True,
        }
        self.assertEqual(evidence_state_for(gpu), "not-tested")

    def test_candidate_module_name_does_not_mean_bound(self) -> None:
        gpu = copy.deepcopy(valid_report()["devices"][0])
        gpu["driver"] = {"status": "available-only", "module": "example"}
        self.assertEqual(evidence_state_for(gpu), "not-tested")

    def test_not_applicable_driver_is_not_binding_evidence(self) -> None:
        display = copy.deepcopy(valid_report()["devices"][1])
        self.assertEqual(display["driver"]["status"], "not-applicable")
        self.assertEqual(evidence_state_for(display), "not-tested")

    def test_failed_functional_test_is_known_problem(self) -> None:
        gpu = copy.deepcopy(valid_report()["devices"][0])
        gpu["functional_tests"] = [
            {"capability": "modeset", "status": "failed"}
        ]
        self.assertEqual(evidence_state_for(gpu), "known-problem")

    def test_required_firmware_error_is_known_problem(self) -> None:
        gpu = copy.deepcopy(valid_report()["devices"][0])
        gpu["firmware"] = {
            "requirement": "required",
            "runtime_status": "load-error",
        }
        self.assertEqual(evidence_state_for(gpu), "known-problem")


class SubsystemSummaryTests(unittest.TestCase):
    def test_real_schema_valid_gpu_report_does_not_claim_certification(self) -> None:
        report = valid_report()
        verdict = classify_subsystem(report, "graphics")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertEqual(verdict.coverage, "reported-device-records")
        self.assertIn("driver-bound-not-tested", verdict.evidence_states)
        self.assertIn("not-tested", verdict.evidence_states)

    def test_partial_passed_functional_test_does_not_certify_subsystem(self) -> None:
        report = valid_report()
        report["devices"] = [copy.deepcopy(report["devices"][0])]
        report["devices"][0]["functional_tests"] = [
            {"capability": "basic-modeset", "status": "passed"}
        ]
        verdict = classify_subsystem(report, "graphics")
        self.assertNotEqual(verdict.level, CERTIFIED)
        self.assertIn(
            "individual tests passed",
            " ".join(verdict.reasons),
        )

    def test_multiple_devices_are_not_certified_by_one_subsystem_function(self) -> None:
        report = valid_report()
        raw = json.dumps(report, ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            evidence = load_validated_profile_evidence(report, raw, evidence_path)
        verdict = classify_subsystem(
            report, "graphics", evidence, report_bytes=raw
        )
        self.assertNotEqual(verdict.level, CERTIFIED)
        self.assertTrue(any("cannot certify multiple" in reason for reason in verdict.reasons))

    def test_missing_subsystem_is_unknown_without_claiming_not_collected(self) -> None:
        report = valid_report()
        report["devices"] = []
        verdict = classify_subsystem(report, "storage")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertFalse(verdict.assessed)
        self.assertEqual(verdict.coverage, "unknown")
        self.assertTrue(any("coverage is unknown" in reason for reason in verdict.reasons))

    def test_invalid_subsystem_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown subsystem"):
            classify_subsystem(valid_report(), "graphics-card")


class ProfileEvidenceTests(unittest.TestCase):
    def test_valid_profile_bundle_bound_to_exact_report_can_certify_single_device(self) -> None:
        report, raw = one_gpu_report()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            evidence = load_validated_profile_evidence(report, raw, evidence_path)
        self.assertIsInstance(evidence, ValidatedProfileEvidence)
        verdict = classify_subsystem(
            report, "graphics", evidence, report_bytes=raw
        )
        self.assertEqual(verdict.level, CERTIFIED)
        self.assertEqual(verdict.evidence_states, ["supported-tested"])

    def test_arbitrary_dictionary_cannot_certify(self) -> None:
        report, _raw = one_gpu_report()
        with self.assertRaisesRegex(TypeError, "raw dictionaries are not trusted"):
            classify_subsystem(
                report,
                "graphics",
                {"verified_functions": [{"name": "graphics", "status": "pass"}]},
            )

    def test_profile_bundle_with_another_report_id_is_rejected(self) -> None:
        report, raw = one_gpu_report()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            document = json.loads(evidence_path.read_text(encoding="utf-8"))
            document["report_id"] = "another-report-id"
            evidence_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ClassificationEvidenceError, "report_id"):
                load_validated_profile_evidence(report, raw, evidence_path)

    def test_profile_bundle_with_changed_source_bytes_is_rejected(self) -> None:
        report, raw = one_gpu_report()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            changed_raw = raw + b"\n"
            with self.assertRaisesRegex(ClassificationEvidenceError, "exact report bytes"):
                load_validated_profile_evidence(report, changed_raw, evidence_path)

    def test_function_name_cannot_appear_twice(self) -> None:
        report, raw = one_gpu_report()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            document = json.loads(evidence_path.read_text(encoding="utf-8"))
            document["verified_functions"].append(
                copy.deepcopy(document["verified_functions"][0])
            )
            evidence_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ClassificationEvidenceError, "duplicate verified"):
                load_validated_profile_evidence(report, raw, evidence_path)

    def test_evidence_cannot_be_reused_for_different_report_bytes(self) -> None:
        report, raw = one_gpu_report()
        with tempfile.TemporaryDirectory() as temporary:
            evidence_path = make_profile_bundle(Path(temporary), report, raw)
            evidence = load_validated_profile_evidence(report, raw, evidence_path)
        changed = raw + b" "
        with self.assertRaisesRegex(ClassificationEvidenceError, "not bound"):
            classify_subsystem(
                report, "graphics", evidence, report_bytes=changed
            )


class ScenarioSeparationTests(unittest.TestCase):
    def test_classification_never_makes_a_scenario_decision(self) -> None:
        report = valid_report()
        result = classify(report, subsystems=["graphics"])
        self.assertEqual(result["decision"], DECISION_NOT_EVALUATED)
        self.assertIn("scenario", result["decision_reason"])

    def test_explanation_does_not_claim_installation_can_or_cannot_continue(self) -> None:
        result = classify(valid_report(), subsystems=["graphics"])
        explanation = explain(result).lower()
        self.assertIn("no installation decision", explanation)
        self.assertNotIn("installation stopped", explanation)
        self.assertNotIn("installation can continue", explanation)

    def test_all_subsystems_are_summarized_without_static_hard_stops(self) -> None:
        result = classify(valid_report())
        self.assertEqual(result["decision"], DECISION_NOT_EVALUATED)
        self.assertEqual(
            set(result["counts"]),
            {CERTIFIED, KNOWN, UNKNOWN},
        )


if __name__ == "__main__":
    unittest.main()
