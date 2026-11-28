# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that release claims are backed by the complete shipped evidence bundle.

The default mode is a release-readiness check: every SHA256SUMS entry must exist
and match, and the artifact named by release-manifest.json must be present.
Metadata-only inspection is explicitly inconclusive and never returns READY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
REQUIRED = ("SHA256SUMS", "release-manifest.json", "boot-bios.json", "boot-uefi.json")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_asset_name(name: object) -> bool:
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    candidate = PurePosixPath(name)
    return (
        not candidate.is_absolute()
        and bool(candidate.parts)
        and all(part not in ("", ".", "..") for part in candidate.parts)
    )


def asset_path(directory: Path, name: str) -> Path:
    return directory.joinpath(*PurePosixPath(name).parts)


def parse_sums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        match = SUM_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"malformed SHA256SUMS line {line_number}")
        name = match.group(2)
        if not safe_asset_name(name):
            raise ValueError(f"unsafe asset path on SHA256SUMS line {line_number}: {name!r}")
        if name == "SHA256SUMS":
            raise ValueError("SHA256SUMS cannot checksum itself")
        if name in sums:
            raise ValueError(f"duplicate SHA256SUMS entry: {name}")
        sums[name] = match.group(1).lower()
    return sums


def read_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def problems(directory: Path, require_iso: bool = True) -> list[str]:
    """Every reason this bundle is not ready; empty means all checks passed."""
    found: list[str] = []
    for name in REQUIRED:
        path = directory / name
        if path.is_symlink():
            found.append(f"{name} must not be a symlink")
        elif not path.is_file():
            found.append(f"missing {name}")
    if found:
        return found

    try:
        sums = parse_sums(directory / "SHA256SUMS")
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid SHA256SUMS: {error}"]
    if not sums:
        return ["SHA256SUMS lists no files"]

    for name in ("release-manifest.json", "boot-bios.json", "boot-uefi.json"):
        if name not in sums:
            found.append(f"{name} is not listed in SHA256SUMS")

    try:
        manifest = read_json_object(directory / "release-manifest.json")
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid release-manifest.json: {error}"]

    artifact = manifest.get("artifact")
    acceptance = manifest.get("acceptance")
    evidence = manifest.get("boot_evidence")
    if not isinstance(artifact, dict):
        found.append("manifest artifact section is missing or invalid")
        artifact = {}
    if not isinstance(acceptance, dict):
        found.append("manifest acceptance section is missing or invalid")
        acceptance = {}
    if evidence is None:
        evidence = {}
    if not isinstance(evidence, dict):
        found.append("manifest boot_evidence section is invalid")
        evidence = {}

    filename = artifact.get("filename")
    if not safe_asset_name(filename):
        found.append("manifest names no safe artifact filename")
        filename = None
    elif filename not in sums:
        found.append(f"{filename} is not listed in SHA256SUMS")
    elif artifact.get("sha256") != sums[filename]:
        found.append(
            f"manifest artifact hash {artifact.get('sha256')} != SHA256SUMS {sums[filename]}"
        )

    for name, expected in sums.items():
        path = asset_path(directory, name)
        if path.is_symlink():
            found.append(f"{name} must not be a symlink")
            continue
        if not path.is_file():
            if require_iso or name != filename:
                found.append(f"{name} is listed in SHA256SUMS but is absent")
            continue
        actual = sha256_of(path)
        if actual != expected:
            found.append(f"{name} does not match its recorded hash")

    if filename is not None and require_iso:
        path = asset_path(directory, filename)
        if not path.is_file():
            found.append(f"{filename} is absent but required")

    for key, name in (("bios_sha256", "boot-bios.json"), ("uefi_sha256", "boot-uefi.json")):
        recorded = evidence.get(key)
        if recorded and sums.get(name) and recorded != sums[name]:
            found.append(f"manifest {key} != SHA256SUMS entry for {name}")

    marker = acceptance.get("marker")
    installer_marker = acceptance.get("installer_marker")
    for platform, name in (("bios", "boot-bios.json"), ("uefi", "boot-uefi.json")):
        try:
            record = read_json_object(directory / name)
        except (OSError, UnicodeError, ValueError) as error:
            found.append(f"invalid {name}: {error}")
            continue
        tail = record.get("serial_output_tail")
        tail = tail if isinstance(tail, str) else ""

        if acceptance.get(platform) == "pass":
            if record.get("boot_confirmed") is not True:
                found.append(f"acceptance.{platform}=pass but {name} has boot_confirmed false")
            if not isinstance(marker, str) or not marker.strip():
                found.append(f"acceptance.{platform}=pass but manifest marker is missing")
            elif marker not in tail:
                found.append(f"acceptance.{platform}=pass but {name} never showed {marker}")

        if acceptance.get("installer") == "pass":
            if record.get("guest_installer_execution") is not True:
                found.append(
                    f"acceptance.installer=pass but {name} has guest_installer_execution false"
                )
            if not isinstance(installer_marker, str) or not installer_marker.strip():
                found.append("acceptance.installer=pass but manifest installer_marker is missing")
            elif installer_marker not in tail:
                found.append(
                    f"acceptance.installer=pass but {name} never showed {installer_marker}"
                )

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a downloaded release bundle against its shipped evidence."
    )
    parser.add_argument("directory", help="directory with the release assets")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="allow a missing ISO for inspection only; the result is never release-ready",
    )
    arguments = parser.parse_args(argv)

    found = problems(Path(arguments.directory), require_iso=not arguments.metadata_only)
    if found:
        print("\n".join(f"release-readiness: {item}" for item in found), file=sys.stderr)
        return 1
    if arguments.metadata_only:
        print(
            "release-readiness: metadata checks passed; ISO not required or accepted (NOT_READY)"
        )
        return 2
    print("release-readiness: manifest claims are backed by the complete shipped evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
