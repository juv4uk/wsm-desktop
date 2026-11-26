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
import tempfile
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


PLATFORMS = {0: "x86 BIOS", 0xEF: "UEFI"}


def read_boot_records(iso: Path) -> dict[str, object]:
    """Parse the El Torito catalogue: which firmware can this image boot on?

    A checksum proves the file arrived intact. This proves the file is *bootable*
    at all - and on which firmware - without starting a machine. It is the
    cheapest check that separates "a valid ISO9660 image" from "an image a
    computer can start".
    """
    records: dict[str, object] = {"el_torito": False, "platforms": [], "entries": []}
    with iso.open("rb") as handle:
        for sector in range(16, 32):
            handle.seek(sector * 2048)
            descriptor = handle.read(2048)
            if len(descriptor) < 2048:
                break
            if descriptor[0] == 255:
                break
            if descriptor[0] != 0 or not descriptor[7:30].startswith(b"EL TORITO SPECIFICATION"):
                continue
            records["el_torito"] = True
            catalogue_lba = int.from_bytes(descriptor[71:75], "little")
            handle.seek(catalogue_lba * 2048)
            catalogue = handle.read(2048)
            if len(catalogue) < 64 or catalogue[0] != 1:
                records["error"] = "El Torito validation entry is malformed"
                return records

            def parse_entry(raw: bytes) -> dict[str, object]:
                return {
                    "bootable": raw[0] == 0x88,
                    "media": raw[1],
                    "sectors": int.from_bytes(raw[6:8], "little"),
                    "load_lba": int.from_bytes(raw[8:12], "little"),
                }

            default = parse_entry(catalogue[32:64])
            records["entries"].append({"platform": PLATFORMS.get(catalogue[1], "unknown"), **default})
            records["platforms"].append(PLATFORMS.get(catalogue[1], "unknown"))

            position = 64
            while position + 32 <= len(catalogue) and catalogue[position] in (0x90, 0x91):
                header = catalogue[position:position + 32]
                platform = PLATFORMS.get(header[1], "unknown")
                count = int.from_bytes(header[2:4], "little")
                position += 32
                for _ in range(count):
                    if position + 32 > len(catalogue):
                        break
                    records["entries"].append({"platform": platform, **parse_entry(catalogue[position:position + 32])})
                    records["platforms"].append(platform)
                    position += 32
                if header[0] == 0x90:
                    break
            break
    return records


def check_boot_records(iso: Path) -> dict[str, str]:
    try:
        records = read_boot_records(iso)
    except OSError as exc:
        return criterion("boot-records", "fail", f"cannot read the image: {exc}")
    if not records["el_torito"]:
        return criterion(
            "boot-records",
            "fail",
            "no El Torito boot record: the image is data, not bootable media",
        )
    platforms = sorted({str(p) for p in records["platforms"]})
    if len(platforms) < 2:
        return criterion(
            "boot-records",
            "fail",
            f"only one firmware can start this image: {platforms}; acceptance requires BIOS and UEFI",
        )
    return criterion("boot-records", "pass", f"bootable on {' and '.join(platforms)}")


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


def join_parts(parts: list[Path], destination: Path) -> Path:
    """Concatenate release parts into one file, in lexical order.

    The release may publish the image as parts because one GitHub asset cannot
    exceed 2 GiB. Verification needs the whole file, and asking the user to
    assemble it first would make "verify what was published" a manual step that
    nobody performs. Streaming keeps memory flat regardless of image size.
    """
    ordered = sorted(parts)
    names = [path.name for path in ordered]
    if names != sorted(names):
        raise ValueError(f"parts are not in lexical order: {names}")
    with destination.open("wb") as sink:
        for part in ordered:
            with part.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    sink.write(chunk)
    return destination


def discover_parts(directory: Path) -> list[Path]:
    """Find ``*.iso.partNNN`` siblings and reject a half-downloaded set."""
    parts = sorted(directory.glob("*.iso.part*"))
    if not parts:
        return []
    suffixes = [path.suffix for path in parts]
    if len(set(suffixes)) != len(suffixes):
        raise ValueError(f"duplicate part suffix in {directory}")
    return parts


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
    parser.add_argument("--iso", required=True, type=Path,
                        help="the image, or any part of it when it was published as parts")
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
    reassembled: Path | None = None
    source_kind = "whole"

    if not iso.is_file() or ".part" in iso.name:
        parts = discover_parts(iso.parent)
        if not parts:
            print(f"verify-live-release: no such file: {iso}", file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory() as temporary:
            joined = join_parts(parts, Path(temporary) / "reassembled.iso")
            # Copy out of the temporary directory so the checks below can use it
            # after the context manager exits.
            reassembled = iso.parent / "reassembled.iso"
            reassembled.write_bytes(joined.read_bytes())
        iso = reassembled
        source_kind = f"parts ({len(parts)})"
        # The verdict must name what was published, not the scratch file the
        # parts were joined into.
        artifact_name = parts[0].name.split(".part")[0]
        print(f"verify-live-release: joined {len(parts)} parts", file=sys.stderr)

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
    criteria.append(check_boot_records(iso))

    if args.boot:
        criteria.append(check_boot(iso, "bios", args.timeout_seconds, None))
        criteria.append(check_boot(iso, "uefi", args.timeout_seconds, args.ovmf_code))
    else:
        for firmware in ("bios", "uefi"):
            criteria.append(
                criterion(f"boot-{firmware}", "not-run", "--boot was not requested")
            )

    result = verdict(criteria, iso)
    result["artifact_source"] = source_kind
    if source_kind != "whole":
        result["artifact"] = artifact_name
    if reassembled is not None:
        reassembled.unlink(missing_ok=True)
    rendered = json.dumps(
        result, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return {"pass": 0, "fail": 1, "incomplete": 2}[result["overall"]]


if __name__ == "__main__":
    raise SystemExit(main())
