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
import hashlib
import json
from datetime import date
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "wsm-profile-evidence/2"

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


def draft(
    report: dict[str, Any],
    vendor: str,
    model: str,
    slug: str,
    report_bytes: bytes,
) -> dict[str, Any]:
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

    collected_on = (report.get("collected_at") or "")[:10]
    try:
        date.fromisoformat(collected_on)
    except ValueError as exc:
        raise SystemExit("draft-profile-evidence: report has no valid collected_at date") from exc

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "profile": {"vendor": vendor, "model": model, "slug": slug},
        "report_id": report_id,
        "report_schema_version": report.get("schema_version", "1.0.0"),
        "isa_level": "unknown",
        "verified_on": collected_on,
        "verified_by": "автори проєкту",
        "verified_functions": functions,
        "known_limitations": problems_from(report) or [],
        "not_assessed": [
            "suspend/resume",
            "graphical session stability over time",
            "audio output and input",
        ],
        "artifacts": [
            {
                "kind": "hardware-report",
                "path": "artifacts/hardware-report.json",
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
                "note": "exact source bytes used to draft this evidence bundle",
            }
        ],
    }

    signature = pci_ids_from(report)
    if signature:
        bundle["hardware_signature"] = {"pci_ids": signature, "match": "all"}

    return bundle


def validate_hardware_report(report: Any) -> list[str]:
    """Apply the published hardware-report schema, including its privacy constants."""
    try:
        schema = json.loads(
            (ROOT / "schemas" / "hardware-report.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load hardware report schema: {exc}"]

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(report), key=lambda item: list(item.absolute_path))
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


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
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="write evidence.json and its source-report artifact under this profile directory",
    )
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report_bytes = args.report.read_bytes()
        report = json.loads(report_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"draft-profile-evidence: cannot read report: {exc}", file=sys.stderr)
        return 2

    report_problems = validate_hardware_report(report)
    if report_problems:
        for problem in report_problems[:20]:
            print(f"draft-profile-evidence: invalid hardware report: {problem}", file=sys.stderr)
        if len(report_problems) > 20:
            print(
                f"draft-profile-evidence: {len(report_problems) - 20} additional schema errors omitted",
                file=sys.stderr,
            )
        return 2

    try:
        bundle = draft(report, args.vendor, args.model, args.slug, report_bytes)
    except (SystemExit, ValueError) as exc:
        print(f"draft-profile-evidence: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(
        bundle, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"

    output = args.out
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output_parent = output.parent.resolve(strict=True)
        if not output_parent.is_dir():
            raise OSError(f"output parent is not a directory: {output_parent}")
        output = output_parent / output.name
        if output.is_symlink() or output.exists():
            raise FileExistsError(f"refusing to overwrite existing evidence file: {output}")

        artifact_path = output_parent / "artifacts" / "hardware-report.json"
        artifact_dir = artifact_path.parent
        if artifact_dir.is_symlink():
            raise OSError(f"artifact directory must not be a symlink: {artifact_dir}")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if artifact_path.is_symlink() or artifact_path.exists():
            raise FileExistsError(f"refusing to overwrite existing report artifact: {artifact_path}")

        with artifact_path.open("xb") as stream:
            stream.write(report_bytes)
        try:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        except Exception:
            artifact_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        print(f"draft-profile-evidence: cannot write bundle: {exc}", file=sys.stderr)
        return 2

    print(
        "draft-profile-evidence: written. Source report bytes are hashed; every function is not-assessed. "
        "Record only real test results, then run make check-profile-evidence.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
