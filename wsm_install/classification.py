# SPDX-License-Identifier: LicenseRef-Volnist
"""Derive a conservative three-level summary from validated hardware evidence.

This module summarizes evidence only. It does not decide whether an installer
scenario may continue: that decision belongs to the canonical scenario policy,
which must consider impact and verified fallbacks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

EVIDENCE_TO_LEVEL = {
    "supported-tested": "certified",
    "driver-bound-not-tested": "known",
    "candidate-only": "unknown",
    "known-problem": "unknown",
    "not-detected": "unknown",
    "not-tested": "unknown",
    "unknown": "unknown",
    "not-collected": "unknown",
}

CERTIFIED = "certified"
KNOWN = "known"
UNKNOWN = "unknown"
DECISION_NOT_EVALUATED = "not-evaluated"

SUBSYSTEMS: dict[str, tuple[str, ...]] = {
    "cpu": ("cpu",),
    "memory": ("memory",),
    "firmware": ("motherboard",),
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


class ClassificationEvidenceError(ValueError):
    """A profile evidence bundle is invalid or does not bind to this report."""


_VALIDATION_TOKEN = object()


@dataclass(frozen=True, init=False)
class ValidatedProfileEvidence:
    """A profile bundle that passed schema, artifact, and exact-report checks.

    Instances are created only by load_validated_profile_evidence(). A plain
    dictionary is deliberately not accepted by the classifier.
    """

    report_id: str
    report_schema_version: str
    report_sha256: str
    function_statuses: tuple[tuple[str, str], ...]

    def __init__(self, token: object, **values: Any) -> None:
        if token is not _VALIDATION_TOKEN:
            raise TypeError(
                "ValidatedProfileEvidence must be created by "
                "load_validated_profile_evidence()"
            )
        for name in (
            "report_id",
            "report_schema_version",
            "report_sha256",
            "function_statuses",
        ):
            object.__setattr__(self, name, values[name])

    def status_for(self, subsystem: str) -> str | None:
        return dict(self.function_statuses).get(subsystem.lower())


def load_validated_profile_evidence(
    report: dict[str, Any],
    report_bytes: bytes,
    evidence_path: Path,
) -> ValidatedProfileEvidence:
    """Validate one profile bundle and bind it to the exact current report.

    The shared profile validator checks JSON Schema, profile.scm bytes, every
    artifact byte stream, safe paths, and functional-evidence references. This
    function adds report identity and raw-byte digest binding.
    """
    if not isinstance(report_bytes, bytes):
        raise TypeError("report_bytes must be the exact source report bytes")
    try:
        decoded_report = json.loads(report_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationEvidenceError(
            f"source report bytes are not valid JSON: {exc}"
        ) from exc
    if decoded_report != report:
        raise ClassificationEvidenceError(
            "report object does not match the supplied source report bytes"
        )

    from wsm_install.profile import (
        EvidenceUnavailable,
        load as load_profile,
        problems as profile_problems,
        slug_matches_directory,
    )

    path = Path(evidence_path)
    try:
        document = load_profile(path)
    except EvidenceUnavailable as exc:
        raise ClassificationEvidenceError(str(exc)) from exc

    root = path.parent
    errors: list[str] = []
    if root.is_symlink() or not root.is_dir():
        errors.append("profile evidence directory is missing or is a symbolic link")

    if document.get("report_id") != report.get("report_id"):
        errors.append("profile evidence report_id does not match the current report")
    if document.get("report_schema_version") != report.get("schema_version"):
        errors.append(
            "profile evidence report_schema_version does not match the current report"
        )

    raw_artifacts = document.get("artifacts")
    if not isinstance(raw_artifacts, list):
        errors.append("profile evidence artifacts must be a list")
        source_reports = []
    else:
        source_reports = [
            item
            for item in raw_artifacts
            if isinstance(item, dict) and item.get("kind") == "wsm-hwcheck-report"
        ]
    if len(source_reports) != 1:
        errors.append(
            "profile evidence must contain exactly one wsm-hwcheck-report artifact"
        )
    else:
        expected_digest = hashlib.sha256(report_bytes).hexdigest()
        if source_reports[0].get("sha256") != expected_digest:
            errors.append(
                "profile evidence source-report SHA-256 does not match the exact report bytes"
            )

    profile_file = root / "profile.scm"
    if root.is_symlink() or profile_file.is_symlink() or not profile_file.is_file():
        errors.append("profile evidence directory has no regular profile.scm")
    else:
        try:
            errors.extend(
                slug_matches_directory(document, root, root.parent.parent)
            )
        except (KeyError, OSError, ValueError) as exc:
            errors.append(f"profile directory identity cannot be verified: {exc}")

    try:
        errors.extend(profile_problems(document, artifact_root=root))
    except EvidenceUnavailable as exc:
        errors.append(str(exc))

    functions = document.get("verified_functions", [])
    normalized: dict[str, str] = {}
    for item in functions if isinstance(functions, list) else []:
        if not isinstance(item, dict):
            errors.append("verified_functions contains a non-object entry")
            continue
        name = str(item.get("name", "")).strip().lower()
        status = str(item.get("status", ""))
        if not name:
            errors.append("verified_functions contains an empty function name")
            continue
        if name in normalized:
            errors.append(f"duplicate verified function name {name!r}")
            continue
        normalized[name] = status

    if errors:
        raise ClassificationEvidenceError("; ".join(errors))

    return ValidatedProfileEvidence(
        _VALIDATION_TOKEN,
        report_id=str(report["report_id"]),
        report_schema_version=str(report["schema_version"]),
        report_sha256=hashlib.sha256(report_bytes).hexdigest(),
        function_statuses=tuple(sorted(normalized.items())),
    )


def _validate_evidence_binding(
    report: dict[str, Any],
    evidence: ValidatedProfileEvidence | None,
    report_bytes: bytes | None,
) -> None:
    if evidence is None:
        return
    if not isinstance(evidence, ValidatedProfileEvidence):
        raise TypeError(
            "profile evidence must be loaded with load_validated_profile_evidence(); "
            "raw dictionaries are not trusted"
        )
    if report_bytes is None:
        raise ValueError("exact report_bytes are required with profile evidence")
    if not isinstance(report_bytes, bytes):
        raise TypeError("report_bytes must be the exact source report bytes")
    try:
        decoded_report = json.loads(report_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassificationEvidenceError(
            f"source report bytes are not valid JSON: {exc}"
        ) from exc
    if decoded_report != report:
        raise ClassificationEvidenceError(
            "report object does not match the exact source report bytes"
        )
    if evidence.report_id != report.get("report_id"):
        raise ClassificationEvidenceError(
            "validated profile evidence belongs to another report_id"
        )
    if evidence.report_schema_version != report.get("schema_version"):
        raise ClassificationEvidenceError(
            "validated profile evidence belongs to another report schema version"
        )
    if evidence.report_sha256 != hashlib.sha256(report_bytes).hexdigest():
        raise ClassificationEvidenceError(
            "validated profile evidence is not bound to these exact report bytes"
        )


def evidence_state_for(device: dict[str, Any]) -> str:
    """Derive conservative device evidence from the real report v1 contract.

    A passed per-capability test is retained as scoped evidence in the report,
    but cannot certify an entire subsystem. A validated profile bundle is
    required for the subsystem-level certified summary.
    """
    tests = [
        item
        for item in device.get("functional_tests", []) or []
        if isinstance(item, dict)
    ]
    if any(item.get("status") == "failed" for item in tests):
        return "known-problem"

    firmware = device.get("firmware") or {}
    if (
        firmware.get("requirement") == "required"
        and firmware.get("runtime_status") in {"missing", "load-error"}
    ):
        return "known-problem"

    driver = device.get("driver") or {}
    if driver.get("status") == "error":
        return "known-problem"

    discovery = device.get("discovery_status", "unknown")
    if discovery == "not-detected":
        return "not-detected"
    if discovery != "discovered":
        return "unknown"

    bound_driver = driver.get("bound_driver")
    if (
        driver.get("status") == "bound"
        and isinstance(bound_driver, str)
        and bool(bound_driver.strip())
    ):
        return "driver-bound-not-tested"

    # module-loaded-unbound, available-only, not-applicable, and a module name
    # without bound-driver evidence do not establish a runtime function.
    return "not-tested"


@dataclass
class SubsystemVerdict:
    subsystem: str
    level: str
    devices: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    assessed: bool = False
    coverage: str = "unknown"
    evidence_states: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "level": self.level,
            "devices": list(self.devices),
            "reasons": list(self.reasons),
            # assessed means that at least one matching device record was
            # classified. It does not claim complete collector coverage.
            "assessed": self.assessed,
            "coverage": self.coverage,
            "evidence_states": list(self.evidence_states),
        }


def _devices_for(report: dict[str, Any], categories: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(categories)
    devices = report.get("devices", [])
    if not isinstance(devices, list):
        raise ValueError("hardware report devices must be a list")
    return [
        device
        for device in devices
        if isinstance(device, dict) and device.get("category") in wanted
    ]


def classify_subsystem(
    report: dict[str, Any],
    subsystem: str,
    evidence: ValidatedProfileEvidence | None = None,
    *,
    report_bytes: bytes | None = None,
) -> SubsystemVerdict:
    if subsystem not in SUBSYSTEMS:
        raise ValueError(f"unknown subsystem: {subsystem}")
    _validate_evidence_binding(report, evidence, report_bytes)

    devices = _devices_for(report, SUBSYSTEMS[subsystem])
    verdict = SubsystemVerdict(
        subsystem=subsystem,
        level=UNKNOWN,
        devices=[str(device.get("device_id", "?")) for device in devices],
        assessed=bool(devices),
        coverage="reported-device-records" if devices else "unknown",
    )

    if not devices:
        verdict.reasons.append(
            "no matching device record; report v1.0.0 has no complete "
            "per-subsystem coverage manifest, so coverage is unknown"
        )
        return verdict

    profile_status = evidence.status_for(subsystem) if evidence else None
    if profile_status == "pass":
        if len(devices) == 1:
            verdict.level = CERTIFIED
            verdict.evidence_states = ["supported-tested"]
            verdict.reasons.append(
                "a schema-valid, artifact-verified profile bundle is bound "
                "to this exact report and covers the single reported device"
            )
            return verdict
        verdict.reasons.append(
            "profile evidence is subsystem-scoped, not device-scoped; it "
            "cannot certify multiple device records without per-device mapping"
        )
    elif profile_status in {"fail", "not-assessed"}:
        verdict.reasons.append(
            f"validated profile evidence records {subsystem} as {profile_status}"
        )

    states: list[str] = []
    for device in devices:
        state = evidence_state_for(device)
        states.append(state)
        identifier = str(device.get("device_id", "?"))
        verdict.reasons.append(f"{identifier}: {state}")

        tests = [
            item
            for item in device.get("functional_tests", []) or []
            if isinstance(item, dict)
        ]
        if any(item.get("status") == "passed" for item in tests):
            capabilities = ", ".join(
                str(item.get("capability", "unspecified"))
                for item in tests
                if item.get("status") == "passed"
            )
            verdict.reasons.append(
                f"{identifier}: individual tests passed ({capabilities}); "
                "this does not certify the whole subsystem"
            )

    verdict.evidence_states = states
    levels = {EVIDENCE_TO_LEVEL.get(state, UNKNOWN) for state in states}
    if levels == {KNOWN}:
        verdict.level = KNOWN
    elif levels <= {KNOWN, CERTIFIED} and KNOWN in levels:
        verdict.level = KNOWN
    else:
        verdict.level = UNKNOWN
    return verdict


def classify(
    report: dict[str, Any],
    evidence: ValidatedProfileEvidence | None = None,
    subsystems: Iterable[str] | None = None,
    *,
    report_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Return evidence levels only; scenario readiness is intentionally omitted."""
    _validate_evidence_binding(report, evidence, report_bytes)
    chosen = list(SUBSYSTEMS) if subsystems is None else list(subsystems)
    verdicts = [
        classify_subsystem(
            report,
            name,
            evidence,
            report_bytes=report_bytes,
        )
        for name in chosen
    ]

    return {
        "schema": "wsm-hardware-classification/1",
        "decision": DECISION_NOT_EVALUATED,
        "decision_reason": (
            "scenario, impact, and verified fallback are not inputs to this "
            "evidence summary; use the canonical scenario capability policy"
        ),
        "counts": {
            CERTIFIED: sum(1 for verdict in verdicts if verdict.level == CERTIFIED),
            KNOWN: sum(1 for verdict in verdicts if verdict.level == KNOWN),
            UNKNOWN: sum(1 for verdict in verdicts if verdict.level == UNKNOWN),
        },
        "subsystems": [verdict.as_dict() for verdict in verdicts],
        "not_assessed": [
            verdict.subsystem for verdict in verdicts if not verdict.assessed
        ],
        "vocabulary": "docs/HARDWARE-COMPATIBILITY-VERDICTS.md (§4.2)",
        "scenario_policy": "docs/INSTALL-CAPABILITY-MATRIX.md",
        "note": (
            "unknown is not a failure. Missing records do not prove that "
            "hardware is absent or incompatible. This summary does not decide "
            "whether an installation scenario may continue."
        ),
    }


def explain(result: dict[str, Any]) -> str:
    """Explain the summary without pretending it is an installation verdict."""
    counts = result["counts"]
    return (
        "Hardware evidence summary: "
        f"{counts[CERTIFIED]} certified, {counts[KNOWN]} known, "
        f"{counts[UNKNOWN]} unknown. No installation decision was made: "
        "the selected scenario, capability impact, and verified fallback "
        "must be evaluated by the canonical scenario policy."
    )
