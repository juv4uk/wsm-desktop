# SPDX-License-Identifier: LicenseRef-Volnist
"""Draft a profile evidence bundle from a hardware report.

Writing the bundle by hand is the reason nobody writes it. This script does the
mechanical part - the report id, the PCI signature, the list of functions the
machine actually exposes, the known problems the report already found - and
leaves the one thing that cannot be automated: saying what a human verified.

Every function starts as ``not-assessed`` on purpose. The draft therefore fails
validation until someone promotes at least one function to ``pass``. That is the
intended workflow: the generator produces a skeleton, the tester produces
evidence.

Usage:

    python3 scripts/draft_profile_evidence.py --report hw.json \\
        --vendor ASUS --model H170-PRO --slug asus/h170-pro --out evidence.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "wsm-profile-evidence/1"

# Device category -> the function a user cares about. Several categories map to
# one function on purpose: "graphics" covers gpu and display.
CATEGORY_TO_FUNCTION = {
    "gpu": "graphics",
    "display": "graphics",
    "storage-controller": "storage",
    "storage-device": "storage",
    "network": "network",
    "audio": "audio",
    "input": "input",
    "bluetooth": "bluetooth",
    "camera": "camera",
    "usb-controller": "usb",
    "memory": "memory",
    "cpu": "cpu",
    "motherboard": "motherboard",
}


def pci_ids_from(report: dict[str, Any]) -> list[str]:
    found: set[str] = set()
    for device in report.get("devices", []):
        identity = device.get("identity") or {}
        for key in ("pci_id", "vendor_device", "vendor:device"):
            value = identity.get(key)
            if isinstance(value, str) and ":" in value:
                found.add(value.lower())
        for item in device.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            for key in ("pci_id", "vendor_device"):
                value = item.get(key)
                if isinstance(value, str) and ":" in value:
                    found.add(value.lower())
    return sorted(found)


def problems_from(report: dict[str, Any]) -> list[str]:
    """Things the report already says are wrong. These are limitations, not guesses."""
    found: list[str] = []
    for device in report.get("devices", []):
        device_id = device.get("device_id", "unknown device")
        status = device.get("discovery_status")
        if status in {"unknown", "not-detected"}:
            found.append(f"{device_id}: discovery status is {status}")
        firmware = device.get("firmware") or {}
        if firmware.get("runtime_status") in {"missing", "load-error"}:
            found.append(
                f"{device_id}: firmware {firmware.get('runtime_status')}"
            )
        for test in device.get("functional_tests") or []:
            if test.get("status") == "failed":
                found.append(f"{device_id}: {test.get('capability')} test failed")
    for warning in report.get("warnings") or []:
        found.append(str(warning))
    return found


def draft(report: dict[str, Any], vendor: str, model: str, slug: str) -> dict[str, Any]:
    functions: list[dict[str, str]] = []
    seen: set[str] = set()
    for device in report.get("devices", []):
        function = CATEGORY_TO_FUNCTION.get(device.get("category", ""), "other")
        if function in seen:
            continue
        seen.add(function)
        functions.append({
            "name": function,
            "status": "not-assessed",
            "note": f"exposed by {device.get('device_id')}; not yet verified by a person",
        })
    if not functions:
        functions.append({"name": "boot", "status": "not-assessed"})

    report_id = report.get("report_id")
    if not report_id:
        raise SystemExit("draft-profile-evidence: report has no report_id")

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "profile": {"vendor": vendor, "model": model, "slug": slug},
        "report_id": report_id,
        "report_schema_version": report.get("schema_version", "1.0.0"),
        "isa_level": "unknown",
        "verified_on": (report.get("collected_at") or "")[:10] or "1970-01-01",
        "verified_by": "автори проєкту",
        "verified_functions": functions,
        "known_limitations": problems_from(report) or [],
        "not_assessed": [
            "suspend/resume",
            "graphical session stability over time",
            "audio output and input",
        ],
        "artifacts": [],
    }

    signature = pci_ids_from(report)
    if signature:
        bundle["hardware_signature"] = {"pci_ids": signature, "match": "all"}

    return bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draft-profile-evidence",
        description=(
            "Draft an evidence bundle skeleton from a hardware report. Every "
            "function starts as not-assessed: the draft fails validation until a "
            "person records what was actually verified."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--vendor", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--slug", required=True, help="lowercase vendor/model, e.g. asus/h170-pro")
    parser.add_argument("--out", type=Path, help="write here instead of stdout")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"draft-profile-evidence: cannot read report: {exc}", file=sys.stderr)
        return 2

    bundle = draft(report, args.vendor, args.model, args.slug)
    rendered = json.dumps(
        bundle, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(
            "draft-profile-evidence: written. Every function is not-assessed: "
            "record what you actually verified, then run make check-profile-evidence.",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
