# SPDX-License-Identifier: LicenseRef-Volnist
"""Verify a published live ISO before anyone is told it works.

The acceptance for the first bootable image is not "the build finished". It is:

1. the published file is the file that was built (checksum matches SHA256SUMS);
2. the release metadata agrees with the artifact it describes;
3. the file really is an ISO9660 image, not an empty or truncated file with the
   right name;
4. the guest reaches the acceptance marker in QEMU in **both** BIOS and UEFI.

This script produces one verdict artifact with a status per criterion, so a
failure names the criterion instead of leaving a reader to interpret a log.

Nothing here is allowed to guess. A check that cannot run is recorded as
`not-run` with the reason, never as a pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "wsm-release-verdict/1"
VERSION = "0.1.0"
MARKER = "WSM_LIVE_READY"
# ISO9660 volume descriptor: "CD001" at sector 16, offset 32769.
ISO_MAGIC_OFFSET = 0x8001
ISO_MAGIC = b"CD001"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sums(path: Path) -> dict[str, str]:
    """Parse a sha256sum-style file into {filename: digest}."""
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0], parts[1].lstrip("*")
        entries[Path(name).name] = digest.lower()
    return entries


def criterion(identifier: str, status: str, detail: str) -> dict[str, str]:
    return {"id": identifier, "status": status, "detail": detail}


def check_checksum(iso: Path, sums: dict[str, str]) -> dict[str, str]:
    expected = sums.get(iso.name)
    if expected is None:
        return criterion("checksum", "fail", f"{iso.name} is not listed in SHA256SUMS")
    actual = sha256_of(iso)
    if actual != expected:
        return criterion(
            "checksum", "fail", f"sha256 mismatch: SHA256SUMS says {expected}, file is {actual}"
        )
    return criterion("checksum", "pass", f"sha256 {actual} matches SHA256SUMS")


def check_manifest(iso: Path, manifest: dict[str, Any], sums: dict[str, str]) -> dict[str, str]:
    entries = manifest.get("files") or manifest.get("artifacts") or []
    named = None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == iso.name:
            named = entry
            break
    if named is None:
        return criterion("manifest", "fail", f"{iso.name} is not described in the release manifest")
    recorded = str(named.get("sha256", "")).lower()
    if recorded and sums.get(iso.name) and recorded != sums[iso.name]:
        return criterion(
            "manifest", "fail", "manifest and SHA256SUMS disagree about the same file"
        )
    return criterion("manifest", "pass", "manifest describes the published file")


def check_iso_structure(iso: Path) -> dict[str, str]:
    size = iso.stat().st_size
    if size < ISO_MAGIC_OFFSET + len(ISO_MAGIC):
        return criterion("iso-structure", "fail", f"file is only {size} bytes")
    with iso.open("rb") as handle:
        handle.seek(ISO_MAGIC_OFFSET)
        magic = handle.read(len(ISO_MAGIC))
    if magic != ISO_MAGIC:
        return criterion(
            "iso-structure",
            "fail",
            "no ISO9660 volume descriptor at sector 16; this is not a bootable ISO",
        )
    return criterion("iso-structure", "pass", f"ISO9660 descriptor present, {size} bytes")


def check_boot(iso: Path, firmware: str, timeout: int, ovmf_code: Path | None) -> dict[str, str]:
    identifier = f"boot-{firmware}"
    smoke = Path(__file__).with_name("qemu_boot_smoke.py")
    if shutil.which("qemu-system-x86_64") is None:
        return criterion(identifier, "not-run", "qemu-system-x86_64 is not installed")
    if firmware == "uefi" and (ovmf_code is None or not ovmf_code.is_file()):
        return criterion(identifier, "not-run", "UEFI needs --ovmf-code and the image is absent")

    command = [
        sys.executable,
        str(smoke),
        "--iso",
        str(iso),
        "--boot-marker",
        MARKER,
        "--timeout-seconds",
        str(timeout),
        "--firmware",
        firmware,
    ]
    if firmware == "uefi":
        command += ["--ovmf-code", str(ovmf_code)]

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout).strip().splitlines()[-1:] or ["no output"]
        return criterion(identifier, "fail", tail[0][:300])
    if MARKER not in completed.stdout:
        return criterion(identifier, "fail", f"boot completed but {MARKER} was never printed")
    return criterion(identifier, "pass", f"{MARKER} observed on the serial console")


def verdict(criteria: list[dict[str, str]], iso: Path) -> dict[str, Any]:
    statuses = {item["status"] for item in criteria}
    if "fail" in statuses:
        overall = "fail"
    elif "not-run" in statuses:
        overall = "incomplete"
    else:
        overall = "pass"
    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "artifact": iso.name,
        "artifact_sha256": sha256_of(iso),
        "overall": overall,
        "criteria": criteria,
        "note": "incomplete is not a pass: a criterion that could not run proves nothing",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify-live-release",
        description="Verify a published live ISO and emit a versioned verdict.",
    )
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--sums", type=Path, help="default: SHA256SUMS next to the ISO")
    parser.add_argument("--manifest", type=Path, help="default: release-manifest.json next to the ISO")
    parser.add_argument("--boot", action="store_true", help="also boot the ISO in QEMU (slow)")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--ovmf-code", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    iso: Path = args.iso
    if not iso.is_file():
        print(f"verify-live-release: no such file: {iso}", file=sys.stderr)
        return 2

    sums_path = args.sums or iso.parent / "SHA256SUMS"
    manifest_path = args.manifest or iso.parent / "release-manifest.json"

    criteria: list[dict[str, str]] = []
    sums: dict[str, str] = {}
    if sums_path.is_file():
        sums = parse_sums(sums_path)
        criteria.append(check_checksum(iso, sums))
    else:
        criteria.append(criterion("checksum", "not-run", f"no {sums_path.name}"))

    if manifest_path.is_file() and sums:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        criteria.append(check_manifest(iso, manifest, sums))
    else:
        criteria.append(criterion("manifest", "not-run", f"no {manifest_path.name}"))

    criteria.append(check_iso_structure(iso))

    if args.boot:
        criteria.append(check_boot(iso, "bios", args.timeout_seconds, None))
        criteria.append(check_boot(iso, "uefi", args.timeout_seconds, args.ovmf_code))
    else:
        for firmware in ("bios", "uefi"):
            criteria.append(
                criterion(f"boot-{firmware}", "not-run", "--boot was not requested")
            )

    result = verdict(criteria, iso)
    rendered = json.dumps(
        result, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return 1 if result["overall"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
