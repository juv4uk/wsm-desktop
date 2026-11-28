# SPDX-License-Identifier: LicenseRef-Volnist
"""Draft an incomplete profile evidence bundle from a hardware report.

The generator copies the exact source report into the bundle's artifacts/
directory and records its SHA-256. It never marks a function as verified:
a person must perform and record functional tests separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "wsm-profile-evidence/2"
REPORT_ARTIFACT = "artifacts/wsm-hwcheck-report.json"

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
    # One implementation, shared with the matcher: two copies of this rule
    # drifted apart once already, and the signature silently stopped being
    # written because the collector's keys were never read here either.
    from wsm_install.profile_match import pci_pairs_from_identity

    found: set[str] = set()
    for device in report.get("devices", []):
        identity = device.get("identity") or {}
        found |= pci_pairs_from_identity(identity)
        for item in device.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            for key in ("pci_id", "vendor_device"):
                value = item.get(key)
                if isinstance(value, str) and ":" in value:
                    found.add(value.lower())
    return sorted(found)


def problems_from(report: dict[str, Any]) -> list[str]:
    """Report issues already observed by the collector; never infer new failures."""
    found: list[str] = []
    for device in report.get("devices", []):
        device_id = device.get("device_id", "unknown device")
        status = device.get("discovery_status")
        if status in {"unknown", "not-detected"}:
            found.append(f"{device_id}: discovery status is {status}")
        firmware = device.get("firmware") or {}
        if firmware.get("runtime_status") in {"missing", "load-error"}:
            found.append(f"{device_id}: firmware {firmware.get('runtime_status')}")
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
    profile_bytes: bytes,
) -> dict[str, Any]:
    """Build a v2 skeleton tied to the exact report and profile source bytes."""
    report_id = report.get("report_id")
    if not isinstance(report_id, str) or len(report_id) < 8:
        raise SystemExit("draft-profile-evidence: report has no valid report_id")
    report_schema_version = report.get("schema_version")
    if not isinstance(report_schema_version, str) or not report_schema_version:
        raise SystemExit("draft-profile-evidence: report has no schema_version")
    collected_at = report.get("collected_at")
    if not isinstance(collected_at, str) or len(collected_at) < 10:
        raise SystemExit("draft-profile-evidence: report has no usable collected_at date")

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

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "profile": {"vendor": vendor, "model": model, "slug": slug},
        "report_id": report_id,
        "report_schema_version": report_schema_version,
        "profile_source": {
            "path": "profile.scm",
            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
        },
        "isa_level": "unknown",
        "verified_on": collected_at[:10],
        "verified_by": "автори проєкту",
        "verified_functions": functions,
        "known_limitations": problems_from(report),
        "not_assessed": [
            "suspend/resume",
            "graphical session stability over time",
            "audio output and input",
        ],
        "artifacts": [{
            "kind": "wsm-hwcheck-report",
            "path": REPORT_ARTIFACT,
            "sha256": hashlib.sha256(report_bytes).hexdigest(),
            "note": "exact source report bytes; this is not a functional compatibility test",
        }],
    }

    signature = pci_ids_from(report)
    if signature:
        bundle["hardware_signature"] = {"pci_ids": signature, "match": "all"}
    return bundle


def write_bundle(
    out: Path,
    report_source: Path,
    report_bytes: bytes,
    profile_bytes: bytes,
    bundle: dict[str, Any],
) -> Path:
    """Write evidence and its source report without overwriting existing files."""
    out = Path(out)
    if out.is_symlink() or out.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence output: {out}")
    parent = out.parent
    if parent.is_symlink() or not parent.is_dir():
        raise OSError(f"profile output directory must already exist and must not be a symlink: {parent}")
    profile_source = parent / "profile.scm"
    if profile_source.is_symlink() or not profile_source.is_file():
        raise OSError(f"regular profile.scm is required before drafting evidence: {profile_source}")

    if profile_source.read_bytes() != profile_bytes:
        raise OSError("profile.scm changed after its evidence digest was calculated")

    artifact_dir = parent / "artifacts"
    if artifact_dir.is_symlink():
        raise OSError(f"artifact directory must not be a symlink: {artifact_dir}")
    artifact_dir.mkdir(exist_ok=True)
    artifact_path = parent / REPORT_ARTIFACT
    if artifact_path.is_symlink() or artifact_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report artifact: {artifact_path}")
    if artifact_path.resolve() == report_source.resolve():
        raise OSError("source report and evidence artifact resolve to the same file")

    created_artifact = False
    created_evidence = False
    try:
        with artifact_path.open("xb") as stream:
            created_artifact = True
            stream.write(report_bytes)
        rendered = json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with out.open("x", encoding="utf-8") as stream:
            created_evidence = True
            stream.write(rendered)
    except Exception:
        if created_evidence:
            try:
                out.unlink()
            except OSError:
                pass
        if created_artifact:
            try:
                artifact_path.unlink()
            except OSError:
                pass
        raise
    return artifact_path


def formats_used(schema: Any) -> set[str]:
    """Every ``format`` the schema asks for, at any depth."""
    found: set[str] = set()
    if isinstance(schema, dict):
        value = schema.get("format")
        if isinstance(value, str):
            found.add(value)
        for item in schema.values():
            found |= formats_used(item)
    elif isinstance(schema, list):
        for item in schema:
            found |= formats_used(item)
    return found


def missing_format_checkers(schema: Any, checker: Any) -> list[str]:
    """Formats the schema declares but this installation cannot check.

    ``jsonschema`` only ships the format checkers that its optional extras
    install. Without ``jsonschema[format]`` the checker object is non-empty but
    knows nothing, and every ``"format": "date-time"`` in the schema becomes a
    comment: an invalid timestamp passes validation silently. That is worse
    than no validation, because the report looks checked.
    """
    return sorted(
        name for name in formats_used(schema) if checker.checkers.get(name) is None
    )


def validate_hardware_report(report: Any) -> list[str]:
    """Validate source report schema and privacy assertions before copying raw bytes."""
    try:
        schema = json.loads(
            (ROOT / "schemas" / "hardware-report.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        return [f"cannot load hardware report schema: {exc}"]

    checker = jsonschema.FormatChecker()
    unchecked = missing_format_checkers(schema, checker)
    if unchecked:
        # Refuse to validate instead of validating less than we claim.
        return [
            "format validation is unavailable for "
            + ", ".join(unchecked)
            + ": install jsonschema[format] (see requirements-install.txt)"
        ]

    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=checker,
    )
    errors = sorted(
        validator.iter_errors(report),
        key=lambda item: list(item.absolute_path),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draft-profile-evidence",
        description=(
            "Draft an evidence v2 skeleton from a hardware report. The exact report is "
            "copied as a hashed artifact. Every function remains not-assessed until a "
            "person performs functional verification."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--vendor", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--slug", required=True, help="lowercase vendor/model, e.g. asus/h170-pro")
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="write evidence.json and artifacts/wsm-hwcheck-report.json; profile.scm must already exist",
    )
    parser.add_argument("--compact", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.report.is_symlink() or not args.report.is_file():
            raise OSError("source report must be a regular non-symlink file")
        report_bytes = args.report.read_bytes()
        report = json.loads(report_bytes)
        profile_source = args.out.parent / "profile.scm"
        if args.out.parent.is_symlink() or not args.out.parent.is_dir():
            raise OSError("profile directory must already exist and must not be a symbolic link")
        if profile_source.is_symlink() or not profile_source.is_file():
            raise OSError("profile directory must contain a regular profile.scm before drafting")
        profile_bytes = profile_source.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"draft-profile-evidence: cannot read source inputs: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("draft-profile-evidence: report root must be a JSON object", file=sys.stderr)
        return 2

    report_problems = validate_hardware_report(report)
    if report_problems:
        for problem in report_problems[:20]:
            print(f"draft-profile-evidence: source report violates privacy/schema contract: {problem}", file=sys.stderr)
        if len(report_problems) > 20:
            print(
                f"draft-profile-evidence: {len(report_problems) - 20} additional schema errors omitted",
                file=sys.stderr,
            )
        return 2

    try:
        bundle = draft(report, args.vendor, args.model, args.slug, report_bytes, profile_bytes)
        artifact = write_bundle(args.out, args.report, report_bytes, profile_bytes, bundle)
    except (OSError, ValueError, SystemExit) as exc:
        print(f"draft-profile-evidence: cannot write evidence draft: {exc}", file=sys.stderr)
        return 2

    print(
        f"draft-profile-evidence: wrote incomplete v2 bundle and source artifact {artifact}; "
        "all functions remain not-assessed, verify the hardware before changing their status.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
