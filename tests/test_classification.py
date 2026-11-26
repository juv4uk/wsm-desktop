# SPDX-License-Identifier: LicenseRef-Volnist
"""Three levels, and the response each one earns.

The failure this prevents is specific: collapsing "we did not check" into
"it is fine". A two-level verdict does that by construction, so these tests
insist on the third level existing and on it producing a decision.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.classification import (  # noqa: E402
    CERTIFIED,
    KNOWN,
    PROCEED,
    STOP,
    UNKNOWN,
    WARN,
    classify,
    classify_subsystem,
    explain,
)


def device(identifier: str, category: str, status: str = "detected", driver: str | None = "some-driver") -> dict:
    entry = {
        "device_id": identifier,
        "category": category,
        "discovery_status": status,
    }
    if driver:
        entry["driver"] = {"name": driver}
    return entry


def report(*devices: dict) -> dict:
    return {"devices": list(devices)}


EVIDENCE_PASS = {
    "verified_functions": [{"name": "storage", "status": "pass"}],
}


class LevelTests(unittest.TestCase):
    def test_discovered_with_driver_is_known_not_certified(self) -> None:
        """A bound driver is not a promise; only evidence is."""
        verdict = classify_subsystem(report(device("d1", "storage-device")), "storage")
        self.assertEqual(verdict.level, KNOWN)

    def test_evidence_pass_makes_it_certified(self) -> None:
        verdict = classify_subsystem(report(device("d1", "storage-device")), "storage", EVIDENCE_PASS)
        self.assertEqual(verdict.level, CERTIFIED)

    def test_evidence_not_assessed_does_not_certify(self) -> None:
        evidence = {"verified_functions": [{"name": "storage", "status": "not-assessed"}]}
        verdict = classify_subsystem(report(device("d1", "storage-device")), "storage", evidence)
        self.assertEqual(verdict.level, KNOWN)
        self.assertTrue(any("not-assessed" in reason for reason in verdict.reasons))

    def test_discovered_without_driver_is_unknown(self) -> None:
        verdict = classify_subsystem(report(device("d1", "gpu", driver=None)), "graphics")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertIn("not-tested", verdict.evidence_states)

    def test_undiscovered_device_is_unknown(self) -> None:
        verdict = classify_subsystem(report(device("d1", "gpu", status="unknown")), "graphics")
        self.assertEqual(verdict.level, UNKNOWN)

    def test_empty_subsystem_is_unknown(self) -> None:
        verdict = classify_subsystem(report(), "audio")
        self.assertEqual(verdict.level, UNKNOWN)
        self.assertFalse(verdict.assessed)
        self.assertTrue(any("does not assess" in reason for reason in verdict.reasons))


class VocabularyTests(unittest.TestCase):
    """The levels are a summary of docs/HARDWARE-COMPATIBILITY-VERDICTS.md."""

    def test_passed_functional_test_maps_to_supported_tested(self) -> None:
        entry = device("d1", "storage-device")
        entry["functional_tests"] = [{"capability": "read-write", "status": "passed"}]
        verdict = classify_subsystem(report(entry), "storage")
        self.assertIn("supported-tested", verdict.evidence_states)

    def test_failed_functional_test_maps_to_known_problem(self) -> None:
        entry = device("d1", "gpu")
        entry["functional_tests"] = [{"capability": "modeset", "status": "failed"}]
        verdict = classify_subsystem(report(entry), "graphics")
        self.assertIn("known-problem", verdict.evidence_states)
        self.assertEqual(verdict.level, UNKNOWN)

    def test_bound_driver_maps_to_driver_bound_not_tested(self) -> None:
        verdict = classify_subsystem(report(device("d1", "network")), "network")
        self.assertIn("driver-bound-not-tested", verdict.evidence_states)

    def test_result_names_the_owning_document(self) -> None:
        result = classify(report())
        self.assertIn("HARDWARE-COMPATIBILITY-VERDICTS.md", result["vocabulary"])


class DecisionTests(unittest.TestCase):
    def test_unknown_storage_stops_the_install(self) -> None:
        """Installing blind onto unknown storage is how data disappears."""
        result = classify(report(device("s1", "storage-device", status="unknown")))
        self.assertEqual(result["decision"], STOP)
        self.assertIn("storage", result["stop_because"])

    def test_unknown_graphics_warns_but_continues(self) -> None:
        result = classify(report(
            device("cpu", "cpu"),
            device("disk", "storage-device"),
            device("gpu", "gpu", driver=None),
        ), subsystems=["cpu", "storage", "graphics"])
        self.assertEqual(result["decision"], WARN)
        self.assertIn("graphics", result["warn_because"])

    def test_unknown_peripheral_only_proceeds(self) -> None:
        result = classify(report(
            device("cpu", "cpu"),
            device("disk", "storage-device"),
            device("usb", "usb-controller", driver=None),
        ), subsystems=["cpu", "storage", "usb"])
        self.assertEqual(result["decision"], PROCEED)
        self.assertEqual(result["counts"][UNKNOWN], 1)

    def test_stop_outranks_warn(self) -> None:
        result = classify(report(
            device("disk", "storage-device", status="unknown"),
            device("gpu", "gpu", driver=None),
        ), subsystems=["storage", "graphics"])
        self.assertEqual(result["decision"], STOP)

    def test_all_certified_proceeds_with_no_warnings(self) -> None:
        evidence = {"verified_functions": [
            {"name": "storage", "status": "pass"},
            {"name": "graphics", "status": "pass"},
        ]}
        result = classify(
            report(device("disk", "storage-device"), device("gpu", "gpu")),
            evidence,
            subsystems=["storage", "graphics"],
        )
        self.assertEqual(result["decision"], PROCEED)
        self.assertEqual(result["counts"][CERTIFIED], 2)


class ExplanationTests(unittest.TestCase):
    def test_stop_explains_what_to_send(self) -> None:
        result = classify(report(device("disk", "storage-device", status="unknown")), subsystems=["storage"])
        text = explain(result)
        self.assertIn("stopped", text)
        self.assertIn("hardware report", text)

    def test_warn_asks_for_agreement(self) -> None:
        result = classify(
            report(device("cpu", "cpu"), device("disk", "storage-device"), device("gpu", "gpu", driver=None)),
            subsystems=["cpu", "storage", "graphics"],
        )
        self.assertIn("agree explicitly", explain(result))

    def test_proceed_says_what_is_recorded(self) -> None:
        result = classify(
            report(device("cpu", "cpu"), device("disk", "storage-device")),
            subsystems=["cpu", "storage"],
        )
        self.assertIn("recorded", explain(result))


class SchemaTests(unittest.TestCase):
    def test_result_declares_its_schema(self) -> None:
        result = classify(report())
        self.assertEqual(result["schema"], "wsm-hardware-classification/1")
        self.assertIn("unknown is not a failure", result["note"])


if __name__ == "__main__":
    unittest.main()
