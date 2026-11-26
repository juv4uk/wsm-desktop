# SPDX-License-Identifier: LicenseRef-Volnist
"""Conservative, read-only summary of the evidence in a WSM hardware report.

This module does not decide whether an installation plan is safe. That decision
belongs to the scenario/capability policy and must account for impact and a
verified fallback. Report v1 has no complete coverage manifest, and profile
evidence v2 does not bind a passed function to a device ID, so this module does
not promote a subsystem to certified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


CERTIFIED = "certified"
KNOWN = "known"
UNKNOWN = "unknown"

# Canonical vocabulary: docs/HARDWARE-COMPATIBILITY-VERDICTS.md (§4.2).
# A report-level device summary can use KNOWN/UNKNOWN only. CERTIFIED is
# deliberately reserved until evidence has exact device/capability scope.
# A passing function test is not enough for subsystem-level certification.
# The canonical policy also requires a validated profile bundle covering all
# critical functions; until that device-scoped contract exists, this state is
# deliberately absent from the summary mapping.
EVIDENCE_TO_LEVEL = {
    "driver-bound-not-tested": KNOWN,
    "candidate-only": KNOWN,
    "known-problem": UNKNOWN,
    "not-detected": UNKNOWN,
    "not-tested": UNKNOWN,
    "unknown": UNKNOWN,
    "not-collected": UNKNOWN,
}

FUNCTIONAL_TEST_TO_EVIDENCE = {
    "passed": "supported-tested",
    "failed": "known-problem",
    "partial": "unknown",
    "not-run": "not-tested",
    "unsupported": "unknown",
    "unknown": "unknown",
}

SUBSYSTEMS: dict[str, tuple[str, ...]] = {
    "cpu": ("cpu",),
    "memory": ("memory",),
    "storage": ("storage-controller", "storage-device"),
    "graphics": ("gpu", "display"),
    "network": ("network",),
    "audio": ("audio",),
    "bluetooth": ("bluetooth",),
    "input": ("input",),
    "usb": ("usb-controller",),
    "camera": ("camera",),
    "other": ("other",),
}


@dataclass
class SubsystemVerdict:
    subsystem: str
    level: str
    devices: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Schema v1 has no complete per-subsystem coverage manifest. Keep this
    # unknown even when some records exist; "observed" is reported separately.
    coverage: str = "unknown"
    observation: str = "no-device-record"
    evidence_states: list[str] = field(default_factory=list)
    functional_tests: list[dict[str, Any]] = field(default_factory=list)
    device_evidence: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "level": self.level,
            "devices": list(self.devices),
            "reasons": list(self.reasons),
            "coverage": self.coverage,
            "observation": self.observation,
            "evidence_states": list(self.evidence_states),
            "functional_tests": [dict(item) for item in self.functional_tests],
            "device_evidence": [dict(item) for item in self.device_evidence],
        }


def _devices_for(report: dict[str, Any], categories: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(categories)
    return [
        device
        for device in report.get("devices", [])
        if isinstance(device, dict) and device.get("category") in wanted
    ]


def evidence_state_for(device: dict[str, Any]) -> str:
    """Summarize discovery and driver facts without confusing module load with binding.

    Functional tests are intentionally handled separately by
    :func:`functional_test_evidence`: one passed capability does not prove every
    function of the device or subsystem.
    """
    discovery = str(device.get("discovery_status", "unknown"))
    if discovery == "not-detected":
        return "not-detected"
    if discovery != "discovered":
        return "unknown"

    driver = device.get("driver")
    if not isinstance(driver, dict):
        return "unknown"

    status = str(driver.get("status", "unknown"))
    bound_driver = str(driver.get("bound_driver") or "").strip()
    candidate = str(driver.get("candidate") or "").strip()

    if status == "bound":
        # The collector represents built-in drivers by bound_driver even when
        # there is no module symlink. Requiring module would create false unknowns.
        return "driver-bound-not-tested" if bound_driver else "unknown"

    if status == "available-only" and candidate:
        return "candidate-only"

    # module-loaded-unbound, a module name, or module_loaded=True alone is not
    # a candidate/binding proof. not-applicable is not a driver failure either.
    if status in {"unknown", "error"}:
        return "unknown"
    return "not-tested"


def functional_test_evidence(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Return each test at its own capability scope; never roll it up to device PASS."""
    device_id = str(device.get("device_id", "?"))
    results: list[dict[str, Any]] = []
    tests = device.get("functional_tests") or []
    if not isinstance(tests, list):
        return results

    for test in tests:
        if not isinstance(test, dict):
            continue
        status = str(test.get("status", "unknown"))
        item: dict[str, Any] = {
            "device_id": device_id,
            "capability": str(test.get("capability", "unknown")),
            "reported_status": status,
            "evidence_state": FUNCTIONAL_TEST_TO_EVIDENCE.get(status, "unknown"),
        }
        # Keep the report's provenance intact. These fields explain how, when,
        # and with what supporting material the capability result was obtained.
        for field_name in ("tested_at", "method", "result", "evidence_refs"):
            if field_name in test:
                value = test[field_name]
                item[field_name] = list(value) if field_name == "evidence_refs" else value
        results.append(item)
    return results


def device_evidence_for(device: dict[str, Any]) -> dict[str, Any]:
    """Preserve per-device provenance without turning observations into verdicts."""
    result: dict[str, Any] = {"device_id": str(device.get("device_id", "?"))}

    driver = device.get("driver")
    if isinstance(driver, dict):
        driver_fields = (
            "status",
            "candidate",
            "module",
            "module_loaded",
            "bound_driver",
            "kernel_config_symbol",
            "notes",
        )
        result["driver"] = {
            key: driver[key] for key in driver_fields if key in driver
        }

    firmware = device.get("firmware")
    if isinstance(firmware, dict):
        firmware_fields = (
            "requirement",
            "runtime_status",
            "files_observed",
            "package_candidates",
            "kernel_log_evidence",
            "redistribution_status",
        )
        result["firmware"] = {
            key: list(firmware[key]) if isinstance(firmware[key], list) else firmware[key]
            for key in firmware_fields
            if key in firmware
        }

    evidence = device.get("evidence")
    if isinstance(evidence, list):
        result["evidence"] = [
            dict(item) for item in evidence if isinstance(item, dict)
        ]

    return result


def classify_subsystem(report: dict[str, Any], subsystem: str) -> SubsystemVerdict:
    """Summarize observed device records; this is not an install-readiness decision."""
    if subsystem not in SUBSYSTEMS:
        raise ValueError(f"unknown subsystem: {subsystem!r}")

    devices = _devices_for(report, SUBSYSTEMS[subsystem])
    identifiers = [str(device.get("device_id", "?")) for device in devices]
    verdict = SubsystemVerdict(
        subsystem=subsystem,
        level=UNKNOWN,
        devices=identifiers,
        observation="device-records-present" if devices else "no-device-record",
    )

    if not devices:
        verdict.reasons.append(
            "no device record is present; report v1 has no coverage manifest, "
            "so absence cannot be interpreted as not-detected or not-collected"
        )
        return verdict

    states: list[str] = []
    tests: list[dict[str, Any]] = []
    device_evidence: list[dict[str, Any]] = []
    for device in devices:
        state = evidence_state_for(device)
        states.append(state)
        tests.extend(functional_test_evidence(device))
        device_evidence.append(device_evidence_for(device))
        verdict.reasons.append(f"{device.get('device_id', '?')}: {state}")

    verdict.evidence_states = states
    verdict.functional_tests = tests
    verdict.device_evidence = device_evidence

    # A summary can be KNOWN only if every observed device has a concrete
    # driver candidate or binding. Any untested/non-applicable/unknown device
    # keeps the subsystem unknown. Functional tests remain capability-scoped.
    has_failed_function = any(
        item["evidence_state"] == "known-problem" for item in tests
    )
    if (
        states
        and not has_failed_function
        and all(state in {"driver-bound-not-tested", "candidate-only"} for state in states)
    ):
        verdict.level = KNOWN
    else:
        verdict.level = UNKNOWN

    return verdict


def classify(
    report: dict[str, Any],
    subsystems: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Produce a diagnostic summary, not a stop/warn/proceed installation verdict."""
    chosen = list(subsystems) if subsystems is not None else list(SUBSYSTEMS)
    if len(chosen) != len(set(chosen)):
        raise ValueError("subsystems must not contain duplicates")

    verdicts = [classify_subsystem(report, name) for name in chosen]
    return {
        "schema": "wsm-hardware-classification/2",
        "subsystems": [verdict.as_dict() for verdict in verdicts],
        "counts": {
            CERTIFIED: 0,
            KNOWN: sum(1 for verdict in verdicts if verdict.level == KNOWN),
            UNKNOWN: sum(1 for verdict in verdicts if verdict.level == UNKNOWN),
        },
        "decision_policy": "docs/INSTALL-CAPABILITY-MATRIX.md",
        "note": (
            "Diagnostic summary only. Report v1 has no complete coverage manifest; "
            "functional-test results apply only to their named capability. This "
            "summary does not choose an installation scenario or authorize a plan."
        ),
    }


def explain(result: dict[str, Any]) -> str:
    """Explain evidence coverage without making an installation decision."""
    unknown = [
        item["subsystem"]
        for item in result.get("subsystems", [])
        if item.get("level") == UNKNOWN
    ]
    known = [
        item["subsystem"]
        for item in result.get("subsystems", [])
        if item.get("level") == KNOWN
    ]
    parts = []
    if known:
        parts.append("Підсистеми з відомим driver binding або candidate: " + ", ".join(known))
    if unknown:
        parts.append("Підсистеми з неповними доказами: " + ", ".join(unknown))
    if not parts:
        parts.append("Звіт не містить підсистем для зведення")
    parts.append(
        "Це діагностичне зведення, а не рішення про готовність до інсталяції."
    )
    return ". ".join(parts) + "."
