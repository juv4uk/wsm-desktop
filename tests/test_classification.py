# SPDX-License-Identifier: LicenseRef-Volnist
"""Classifier tests use the real report shape and keep evidence scope explicit."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.classification import (  # noqa: E402
    CERTIFIED,
    EVIDENCE_TO_LEVEL,
    KNOWN,
    UNKNOWN,
    classify,
    classify_subsystem,
    evidence_state_for,
    explain,
)


def device(
    identifier: str,
    category: str,
    *,
    discovery: str = "discovered",
    driver_status: str = "bound",
    bound_driver: str | None = "test-driver",
    module: str | None = None,
    module_loaded: bool | None = None,
    candidate: str | None = None,
    functional_tests: list[dict[str, str]] | None = None,
) -> dict:
    driver = {"status": driver_status}
    if bound_driver is not None:
        driver["bound_driver"] = bound_driver
    if module is not None:
        driver["module"] = module
    if module_loaded is not None:
        driver["module_loaded"] = module_loaded
    if candidate is not None:
        driver["candidate"] = candidate
    return {
        "device_id": identifier,
        "category": category,
        "discovery_status": discovery,
        "driver": driver,
        "functional_tests": functional_tests or [],
    }


def report(*devices: dict) -> dict:
    return {"devices": list(devices)}


class ProductionDriverContractTests(unittest.TestCase):
    def test_schema_valid_desktop_fixture_uses_bound_driver_field(self) -> None:
        path = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        gpu = next(item for item in value["devices"] if item["category"] == "gpu")
        self.assertEqual(evidence_state_for(gpu), "driver-bound-not-tested")

    def test_builtin_bound_driver_does_not_require_module(self) -> None:
        value = device(
            "cpu-bound",
            "cpu",
            driver_status="bound",
            bound_driver="built-in-test",
            module=None,
        )
        self.assertEqual(evidence_state_for(value), "driver-bound-not-tested")

    def test_module_loaded_unbound_is_not_binding(self) -> None:
        value = device(
            "gpu-unbound",
            "gpu",
            driver_status="module-loaded-unbound",
            bound_driver=None,
            module="nvidia",
            module_loaded=True,
        )
        self.assertEqual(evidence_state_for(value), "not-tested")

    def test_available_only_requires_an_explicit_candidate(self) -> None:
        without_candidate = device(
            "wifi-no-candidate",
            "network",
            driver_status="available-only",
            bound_driver=None,
        )
        with_candidate = device(
            "wifi-candidate",
            "network",
            driver_status="available-only",
            bound_driver=None,
            candidate="iwlwifi",
        )
        self.assertEqual(evidence_state_for(without_candidate), "not-tested")
        self.assertEqual(evidence_state_for(with_candidate), "candidate-only")

    def test_bound_without_bound_driver_is_unknown(self) -> None:
        value = device(
            "gpu-inconsistent",
            "gpu",
            driver_status="bound",
            bound_driver=None,
            module="nvidia",
            module_loaded=True,
        )
        self.assertEqual(evidence_state_for(value), "unknown")

    def test_not_applicable_is_not_a_driver_failure(self) -> None:
        value = device(
            "display-connector",
            "display",
            driver_status="not-applicable",
            bound_driver=None,
        )
        self.assertEqual(evidence_state_for(value), "not-tested")


class CapabilityScopeTests(unittest.TestCase):
    def test_passed_functional_test_does_not_certify_the_device(self) -> None:
        value = device(
            "gpu-0",
            "gpu",
            functional_tests=[{"capability": "display-mode", "status": "passed"}],
        )
        verdict = classify_subsystem(report(value), "graphics")
        self.assertEqual(verdict.level, KNOWN)
        self.assertEqual(verdict.functional_tests, [{
            "device_id": "gpu-0",
            "capability": "display-mode",
            "reported_status": "passed",
            "evidence_state": "supported-tested",
        }])
        self.assertNotEqual(verdict.level, CERTIFIED)

    def test_one_pass_does_not_cover_another_device_in_same_subsystem(self) -> None:
        first = device(
            "gpu-0",
            "gpu",
            functional_tests=[{"capability": "display-mode", "status": "passed"}],
        )
        second = device("gpu-1", "gpu", driver_status="none-known", bound_driver=None)
        verdict = classify_subsystem(report(first, second), "graphics")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertEqual(verdict.devices, ["gpu-0", "gpu-1"])
        self.assertEqual(len(verdict.functional_tests), 1)

    def test_failed_function_is_reported_without_poisoning_other_capabilities(self) -> None:
        value = device(
            "gpu-0",
            "gpu",
            functional_tests=[
                {"capability": "display-mode", "status": "passed"},
                {"capability": "gpu-render", "status": "failed"},
            ],
        )
        verdict = classify_subsystem(report(value), "graphics")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertEqual(
            [item["evidence_state"] for item in verdict.functional_tests],
            ["supported-tested", "known-problem"],
        )

    def test_raw_profile_dict_is_not_an_input_to_the_classifier(self) -> None:
        value = device("storage-0", "storage-device")
        with self.assertRaises(TypeError):
            classify_subsystem(
                report(value),
                "storage",
                {"verified_functions": [{"name": "storage", "status": "pass"}]},
            )


class CoverageAndPolicyTests(unittest.TestCase):
    def test_missing_subsystem_keeps_coverage_unknown(self) -> None:
        verdict = classify_subsystem(report(), "storage")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertEqual(verdict.coverage, "unknown")
        self.assertEqual(verdict.observation, "no-device-record")
        self.assertTrue(any("no coverage manifest" in item for item in verdict.reasons))

    def test_present_records_do_not_imply_complete_coverage(self) -> None:
        verdict = classify_subsystem(
            report(device("disk-0", "storage-device")),
            "storage",
        )
        self.assertEqual(verdict.level, KNOWN)
        self.assertEqual(verdict.coverage, "unknown")
        self.assertEqual(verdict.observation, "device-records-present")

    def test_candidate_only_matches_canonical_policy(self) -> None:
        self.assertEqual(EVIDENCE_TO_LEVEL["candidate-only"], KNOWN)

    def test_classifier_does_not_return_an_install_decision(self) -> None:
        value = classify(report(device("disk-0", "storage-device")))
        self.assertEqual(value["schema"], "wsm-hardware-classification/2")
        self.assertNotIn("decision", value)
        self.assertEqual(value["decision_policy"], "docs/INSTALL-CAPABILITY-MATRIX.md")

    def test_no_scenario_is_inferred_from_subsystem_name(self) -> None:
        offline = classify(report(device("wifi-0", "network", discovery="unknown")), ["network"])
        local = classify(report(device("wifi-0", "network", discovery="unknown")), ["network"])
        self.assertEqual(offline, local)
        self.assertNotIn("decision", offline)

    def test_explanation_is_diagnostic_not_a_stop_or_warning(self) -> None:
        value = classify(report())
        message = explain(value)
        self.assertIn("діагностичне зведення", message.lower())
        self.assertNotIn("installation stopped", message.lower())


if __name__ == "__main__":
    unittest.main()
