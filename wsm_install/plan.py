# SPDX-License-Identifier: LicenseRef-Volnist
"""Pure functions for evidence interpretation and deterministic plan generation."""

from __future__ import annotations

import hashlib
import json
from typing import Any


CRITICAL_REQUIRED = {"boot-path", "primary-display", "input"}
USER_SELECTION_REQUIRED = {"storage-install-target"}


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for hashing and reproducible output."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def summarize_report(report: dict[str, Any]) -> str:
    env = report["environment"]
    devices = report["devices"]
    discovered = sum(item["discovery_status"] == "discovered" for item in devices)
    unknown = sum(item["discovery_status"] == "unknown" for item in devices)
    lines = [
        f"WSM hardware preflight — report {report['report_id']}",
        f"Schema: {report['schema_version']} | collected: {report['collected_at']}",
        f"Environment: {env['architecture']} | kernel {env['kernel_release']} | boot {env['boot_mode']} | virtualization {env['virtualization']}",
        f"Devices: {len(devices)} total, {discovered} discovered, {unknown} unknown",
    ]
    for device in devices:
        identity = device.get("identity", {})
        label = identity.get("model") or identity.get("manufacturer") or device["device_id"]
        test_summary = ", ".join(
            f"{test['capability']}={test['status']}"
            for test in device["functional_tests"]
        ) or "none"
        evidence = device.get("evidence", [])
        provenance = (
            f"source={evidence[0]['source']} @ {evidence[0]['observed_at']} "
            f"({evidence[0]['confidence']})"
            if evidence else "source=unknown"
        )
        lines.append(
            f"- {device['category']}: {label}; discovery={device['discovery_status']}; "
            f"driver={device['driver']['status']}; firmware={device['firmware']['runtime_status']}; "
            f"tests=[{test_summary}]; {provenance}"
        )
    if report.get("warnings"):
        lines.append("Report warnings: " + "; ".join(report["warnings"]))
    return "\n".join(lines)


def build_plan(
    report: dict[str, Any],
    report_bytes: bytes,
    backend: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Build a backend-specific plan without probing or invoking a backend."""
    blockers: list[str] = []
    warnings: list[str] = []

    for device in report["devices"]:
        criticality = set(device.get("criticality", []))
        if criticality & CRITICAL_REQUIRED and device["discovery_status"] in {"unknown", "not-detected"}:
            blockers.append(
                f"{device['device_id']}: required critical device discovery is "
                f"{device['discovery_status']}"
            )
        firmware = device["firmware"]
        if (
            firmware["requirement"] == "required"
            and firmware["runtime_status"] in {"missing", "load-error"}
        ):
            message = (
                f"{device['device_id']}: required runtime firmware is "
                f"{firmware['runtime_status']}"
            )
            if criticality & CRITICAL_REQUIRED:
                blockers.append(message)
            else:
                warnings.append(message)
        if criticality & {"network-installation"} and not any(
            test.get("status") == "passed"
            for test in device["functional_tests"]
            if test.get("capability") in {"network-link", "network-connectivity"}
        ):
            warnings.append(
                f"{device['device_id']}: network installation path is not functionally tested; "
                "offline installation may be required"
            )

    for warning in report.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)

    observed_roles = {
        role
        for device in report["devices"]
        for role in device.get("criticality", [])
    }
    role_coverage = {
        role: ("observed" if role in observed_roles else "not-collected")
        for role in sorted(CRITICAL_REQUIRED)
    }
    missing_roles = sorted(role for role, state in role_coverage.items() if state != "observed")
    for role in missing_roles:
        warnings.append(f"required role {role!r} is not represented in the report; plan remains diagnostic-only")
    warnings.append(
        "storage target is not selected by hardware discovery; explicit user selection and immediate identity revalidation are still required"
    )

    backend_id = {"guix": "guix-system", "nix": "nixos"}[backend]
    plan: dict[str, Any] = {
        "plan_version": "0.1.0",
        "plan_mode": "dry-run",
        "plan_status": "diagnostic-only",
        "plan_readiness": {
            "confirmable": False,
            "missing_required_roles": missing_roles,
            "role_coverage": role_coverage,
            "required_user_actions": sorted(USER_SELECTION_REQUIRED),
        },
        "backend": {"id": backend_id},
        "source_report": {
            "schema_version": report["schema_version"],
            "report_id": report["report_id"],
            "sha256": hashlib.sha256(report_bytes).hexdigest(),
        },
        "environment": {
            "architecture": report["environment"]["architecture"],
            "kernel_release": report["environment"]["kernel_release"],
            "boot_mode": report["environment"]["boot_mode"],
            "virtualization": report["environment"]["virtualization"],
        },
        "device_summary": [
            {
                "device_id": device["device_id"],
                "category": device["category"],
                "criticality": sorted(device.get("criticality", [])),
                "discovery_status": device["discovery_status"],
                "driver_status": device["driver"]["status"],
                "firmware_requirement": device["firmware"]["requirement"],
                "firmware_runtime_status": device["firmware"]["runtime_status"],
                "functional_tests": [
                    {"capability": test["capability"], "status": test["status"]}
                    for test in device["functional_tests"]
                ],
                "evidence_refs": [
                    {"json_pointer": f"/devices/{device_index}/evidence/{evidence_index}"}
                    for evidence_index, _ in enumerate(device.get("evidence", []))
                ],
                "functional_test_refs": [
                    {"json_pointer": f"/devices/{device_index}/functional_tests/{test_index}"}
                    for test_index, _ in enumerate(device["functional_tests"])
                ],
            }
            for device_index, device in enumerate(report["devices"])
        ],
        "warnings": warnings,
        "blockers": blockers,
        "execution": {
            "dry_run": True,
            "plan_confirmable": False,
            "mutations_authorized": False,
            "backend_invoked": False,
            "disk_access_performed": False,
        },
    }
    # Hash canonical plan bytes before adding the digest field.
    plan["plan_sha256"] = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return plan, blockers, warnings
