# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that a release draft's claims are backed by its own evidence.

`release-manifest.json` says things like `"installer": "pass"`. Until now nothing
compared that claim with the boot records shipped beside it: the manifest could
say a marker was seen while `boot-bios.json` recorded
`guest_installer_execution: false`, and every gate would stay green — issue #613
exists precisely because that gap once reached the outside world.

This checker needs no ISO and no QEMU. It reads only the small JSON files and
`SHA256SUMS` that a draft carries, so it can run before anything is published.

Rules:

* every file named in `SHA256SUMS` that is present must match its hash;
* the manifest's artifact hash must be the one in `SHA256SUMS`;
* the recorded boot-evidence hashes must match the files actually shipped;
* an `acceptance` entry of `pass` must be backed by the corresponding boot
  record: the marker in the serial output and, for the installer, an executed
  entrypoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
REQUIRED = ("SHA256SUMS", "release-manifest.json", "boot-bios.json", "boot-uefi.json")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SUM_LINE.match(line.strip())
        if match:
            sums[match.group(2)] = match.group(1).lower()
    return sums


def problems(directory: Path, require_iso: bool = False) -> list[str]:
    """Every reason this draft must not be published. Empty list means ready."""
    found: list[str] = []
    for name in REQUIRED:
        if not (directory / name).is_file():
            found.append(f"missing {name}")
    if found:
        return found

    sums = parse_sums(directory / "SHA256SUMS")
    if not sums:
        return ["SHA256SUMS lists no files"]

    manifest = json.loads((directory / "release-manifest.json").read_text(encoding="utf-8"))
    artifact = manifest.get("artifact") or {}
    acceptance = manifest.get("acceptance") or {}
    evidence = manifest.get("boot_evidence") or {}

    filename = artifact.get("filename")
    if not filename:
        found.append("manifest names no artifact")
    else:
        if filename not in sums:
            found.append(f"{filename} is not listed in SHA256SUMS")
        elif artifact.get("sha256") != sums[filename]:
            found.append(
                f"manifest artifact hash {artifact.get('sha256')} != SHA256SUMS {sums[filename]}"
            )
        iso = directory / filename
        if iso.is_file():
            if sha256_of(iso) != sums[filename]:
                found.append(f"{filename} does not match its recorded hash")
        elif require_iso:
            found.append(f"{filename} is absent but required")

    for key, name in (("bios_sha256", "boot-bios.json"), ("uefi_sha256", "boot-uefi.json")):
        recorded = evidence.get(key)
        if recorded and sums.get(name) and recorded != sums[name]:
            found.append(f"manifest {key} != SHA256SUMS entry for {name}")

    for platform, name in (("bios", "boot-bios.json"), ("uefi", "boot-uefi.json")):
        record = json.loads((directory / name).read_text(encoding="utf-8"))
        tail = str(record.get("serial_output_tail") or "")
        marker = acceptance.get("marker")
        installer_marker = acceptance.get("installer_marker")
        if acceptance.get(platform) == "pass":
            if record.get("boot_confirmed") is not True:
                found.append(f"acceptance.{platform}=pass but {name} has boot_confirmed false")
            if marker and marker not in tail:
                found.append(f"acceptance.{platform}=pass but {name} never showed {marker}")
        if acceptance.get("installer") == "pass":
            if record.get("guest_installer_execution") is not True:
                found.append(
                    f"acceptance.installer=pass but {name} has guest_installer_execution false"
                )
            if installer_marker and installer_marker not in tail:
                found.append(
                    f"acceptance.installer=pass but {name} never showed {installer_marker}"
                )

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a downloaded release draft against its own evidence."
    )
    parser.add_argument("directory", help="directory with the draft's assets")
    parser.add_argument(
        "--require-iso",
        action="store_true",
        help="fail when the image itself is absent (slower: it hashes the ISO)",
    )
    arguments = parser.parse_args(argv)

    found = problems(Path(arguments.directory), require_iso=arguments.require_iso)
    if found:
        print("\n".join(f"release-readiness: {item}" for item in found), file=sys.stderr)
        return 1
    print("release-readiness: manifest claims are backed by the shipped evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
