# SPDX-License-Identifier: LicenseRef-Volnist
"""Match a hardware report against profile evidence bundles.

The installer could already refuse a broken bundle, but it could not answer the
simpler question: does a verified profile exist for *this* machine at all?

Matching is deliberately strict and dumb. It compares PCI vendor:device pairs
from the report against the signature each profile declares, and it refuses to
guess:

* no signature means the profile cannot be matched automatically - it can still
  be applied by hand, but the installer will not claim it applies;
* a partial match is not a match unless the profile says ``match: any``;
* two profiles matching the same machine is reported as ambiguous, not resolved
  by picking one.

Guessing here would defeat the point of evidence: a wrong profile is worse than
no profile, because it looks verified.
"""

from __future__ import annotations

from typing import Any, Iterable

PCI_KEYS = ("pci_id", "pci_ids", "address", "identity")


def _pci_ids_from_device(device: dict[str, Any]) -> set[str]:
    """Collect every vendor:device pair the report exposes for one device."""
    found: set[str] = set()
    identity = device.get("identity") or {}
    for key in ("pci_id", "vendor_device", "vendor:device"):
        value = identity.get(key)
        if isinstance(value, str) and ":" in value:
            found.add(value.lower())
    evidence = device.get("evidence") or []
    for item in evidence:
        for key in ("pci_id", "vendor_device"):
            value = item.get(key) if isinstance(item, dict) else None
            if isinstance(value, str) and ":" in value:
                found.add(value.lower())
    return found


def report_pci_ids(report: dict[str, Any]) -> set[str]:
    """All PCI vendor:device pairs present in a hardware report."""
    found: set[str] = set()
    for device in report.get("devices", []):
        found |= _pci_ids_from_device(device)
    return found


def match(
    report: dict[str, Any],
    bundles: Iterable[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """Return (matched, ambiguous, skipped) slug lists for a report.

    ``skipped`` explains why a bundle was not considered, so the caller can say
    "we have three profiles, none of them for this machine" instead of silence.
    """
    present = report_pci_ids(report)
    matched: list[str] = []
    ambiguous: list[str] = []
    skipped: list[str] = []

    for bundle in bundles:
        slug = bundle.get("profile", {}).get("slug", "<unknown>")
        signature = bundle.get("hardware_signature")
        if not signature:
            skipped.append(f"{slug}: no hardware signature")
            continue

        wanted = {value.lower() for value in signature.get("pci_ids", [])}
        mode = signature.get("match", "all")
        if mode == "any":
            ok = bool(wanted & present)
        else:
            ok = wanted <= present

        if not ok:
            skipped.append(f"{slug}: signature does not match this machine")
        elif slug in matched:
            continue
        else:
            matched.append(slug)

    if len(matched) > 1:
        ambiguous = matched
        matched = []

    return matched, ambiguous, skipped
