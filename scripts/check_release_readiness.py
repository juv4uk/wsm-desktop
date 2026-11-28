# SPDX-License-Identifier: LicenseRef-Volnist
"""Fail-closed validation of a complete WSM Minimal Live release bundle.

The checker runs after the workflow has finalized the manifest and SHA256SUMS,
including the whole-ISO or multipart publication representation. An empty
problem list means the shipped evidence supports the release claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = (
    "SHA256SUMS",
    "build-manifest.json",
    "release-manifest.json",
    "boot-bios.json",
    "boot-uefi.json",
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_sha256(paths: list[Path]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for path in paths:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    return digest.hexdigest(), size


def safe_asset_name(name: object) -> bool:
    """Release assets are flat filenames; nested paths and traversal are refused."""
    return (
        isinstance(name, str)
        and bool(name)
        and name not in {".", ".."}
        and "/" not in name
        and "\\" not in name
        and not any(ord(character) < 32 or ord(character) == 127 for character in name)
    )


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
            raise ValueError(f"unsafe asset name on SHA256SUMS line {line_number}: {name!r}")
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


def problems(directory: Path, metadata_only: bool = False) -> list[str]:
    """Return every reason the final release bundle is not ready."""
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

    for name in REQUIRED[1:]:
        if name not in sums:
            found.append(f"{name} is not listed in SHA256SUMS")

    try:
        manifest = read_json_object(directory / "release-manifest.json")
        read_json_object(directory / "build-manifest.json")
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid release metadata: {error}"]

    artifact = manifest.get("artifact")
    acceptance = manifest.get("acceptance")
    evidence = manifest.get("boot_evidence")
    if not isinstance(artifact, dict):
        found.append("manifest artifact section is missing or invalid")
        artifact = {}
    if not isinstance(acceptance, dict):
        found.append("manifest acceptance section is missing or invalid")
        acceptance = {}
    if not isinstance(evidence, dict):
        found.append("manifest boot_evidence section is missing or invalid")
        evidence = {}

    filename = artifact.get("filename")
    artifact_sha = artifact.get("sha256")
    artifact_bytes = artifact.get("bytes")
    published_as = artifact.get("published_as", "whole")
    if not safe_asset_name(filename):
        found.append("manifest names no safe artifact filename")
        filename = None
    if not isinstance(artifact_sha, str) or SHA256.fullmatch(artifact_sha) is None:
        found.append("manifest artifact sha256 is missing or malformed")
        artifact_sha = None
    if not isinstance(artifact_bytes, int) or isinstance(artifact_bytes, bool) or artifact_bytes <= 0:
        found.append("manifest artifact bytes is missing or invalid")
        artifact_bytes = None

    parts: list[str] = []
    if published_as == "whole":
        if filename is not None:
            if filename not in sums:
                found.append(f"{filename} is not listed in SHA256SUMS")
            elif artifact_sha is not None and sums[filename] != artifact_sha:
                found.append(
                    f"manifest artifact hash {artifact_sha} != SHA256SUMS {sums[filename]}"
                )
            stale_parts = sorted(path.name for path in directory.glob(filename + ".part*"))
            if stale_parts:
                found.append(f"whole-ISO bundle contains unexpected split parts: {stale_parts}")
    elif published_as == "parts":
        raw_parts = artifact.get("parts")
        count = artifact.get("parts_count")
        if not isinstance(raw_parts, list) or not raw_parts:
            found.append("multipart artifact has no parts list")
        else:
            for index, part in enumerate(raw_parts):
                if not safe_asset_name(part):
                    found.append(f"multipart artifact has unsafe part name at index {index}")
                elif part in parts:
                    found.append(f"multipart artifact repeats part {part}")
                else:
                    parts.append(part)
            if parts != sorted(parts):
                found.append("multipart artifact parts are not in lexical concatenation order")
        if not isinstance(count, int) or isinstance(count, bool) or count != len(parts):
            found.append("multipart artifact parts_count does not match its parts list")
        if filename is not None and filename in sums:
            found.append("original ISO filename is listed even though artifact is published as parts")
        expected_parts = (
            [f"{filename}.part{index:03d}" for index in range(len(parts))]
            if filename is not None else []
        )
        if parts != expected_parts:
            found.append("multipart artifact parts are missing, extra, or not contiguously numbered")
        for part in parts:
            if part not in sums:
                found.append(f"multipart part {part} is not listed in SHA256SUMS")
        if "ISO-CHECKSUMS.sha256" not in sums:
            found.append("ISO-CHECKSUMS.sha256 is not listed in SHA256SUMS")
        unexpected_parts = sorted(
            path.name for path in directory.glob((filename or "") + ".part*")
            if path.name not in parts
        )
        if unexpected_parts:
            found.append(f"multipart bundle contains unexpected split parts: {unexpected_parts}")
    else:
        found.append(f"unsupported artifact published_as value: {published_as!r}")

    # Every published asset in SHA256SUMS must exist as a regular, non-symlink
    # file and match its own digest. The sole exception is explicit metadata-only
    # inspection of the missing whole ISO; it is never release-ready.
    for name, expected in sums.items():
        path = directory / name
        if path.is_symlink():
            found.append(f"{name} must not be a symlink")
            continue
        if not path.is_file():
            if metadata_only and published_as == "whole" and name == filename:
                continue
            found.append(f"{name} is listed in SHA256SUMS but is absent")
            continue
        actual = sha256_of(path)
        if actual != expected:
            found.append(f"{name} does not match its recorded hash")

    if published_as == "whole" and filename is not None:
        path = directory / filename
        if path.is_symlink():
            found.append(f"{filename} must not be a symlink")
        elif path.is_file():
            actual_size = path.stat().st_size
            if artifact_bytes is not None and actual_size != artifact_bytes:
                found.append(
                    f"manifest artifact bytes {artifact_bytes} != actual bytes {actual_size}"
                )
            if artifact_sha is not None and sha256_of(path) != artifact_sha:
                found.append("manifest artifact sha256 does not match the ISO")
        elif not metadata_only:
            found.append(f"{filename} is absent but required")

    if published_as == "parts" and parts and all((directory / part).is_file() for part in parts):
        if any((directory / part).is_symlink() for part in parts):
            found.append("multipart artifact contains a symlink")
        else:
            actual_sha, actual_size = combined_sha256([directory / part for part in parts])
            if artifact_sha is not None and actual_sha != artifact_sha:
                found.append("concatenated artifact parts do not match manifest artifact sha256")
            if artifact_bytes is not None and actual_size != artifact_bytes:
                found.append(
                    f"manifest artifact bytes {artifact_bytes} != concatenated part bytes {actual_size}"
                )
            sidecar = directory / "ISO-CHECKSUMS.sha256"
            if sidecar.is_file() and not sidecar.is_symlink():
                expected_sidecar = "".join(
                    f"{sha256_of(directory / part)}  {part}\\n" for part in parts
                )
                try:
                    actual_sidecar = sidecar.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as error:
                    found.append(f"cannot read ISO-CHECKSUMS.sha256: {error}")
                else:
                    if actual_sidecar != expected_sidecar:
                        found.append("ISO-CHECKSUMS.sha256 does not match the ordered part list")

    expected_build_sha = manifest.get("build_manifest_sha256")
    if not isinstance(expected_build_sha, str) or SHA256.fullmatch(expected_build_sha) is None:
        found.append("manifest build_manifest_sha256 is missing or malformed")
    elif sums.get("build-manifest.json") != expected_build_sha:
        found.append("manifest build_manifest_sha256 != SHA256SUMS build-manifest.json")

    for key, name in (("bios_sha256", "boot-bios.json"), ("uefi_sha256", "boot-uefi.json")):
        recorded = evidence.get(key)
        if not isinstance(recorded, str) or SHA256.fullmatch(recorded) is None:
            found.append(f"manifest boot_evidence.{key} is missing or malformed")
        elif sums.get(name) != recorded:
            found.append(f"manifest boot_evidence.{key} != SHA256SUMS entry for {name}")

    for key in ("bios", "uefi", "installer"):
        if acceptance.get(key) != "pass":
            found.append(f"manifest acceptance.{key} is not pass")

    marker = acceptance.get("marker")
    installer_marker = acceptance.get("installer_marker")
    if not isinstance(marker, str) or not marker.strip():
        found.append("manifest acceptance.marker is missing")
        marker = None
    if not isinstance(installer_marker, str) or not installer_marker.strip():
        found.append("manifest acceptance.installer_marker is missing")
        installer_marker = None

    for platform, name in (("bios", "boot-bios.json"), ("uefi", "boot-uefi.json")):
        try:
            record = read_json_object(directory / name)
        except (OSError, UnicodeError, ValueError) as error:
            found.append(f"invalid {name}: {error}")
            continue
        tail = record.get("serial_output_tail")
        tail = tail if isinstance(tail, str) else ""
        if record.get("boot_confirmed") is not True:
            found.append(f"{name} has boot_confirmed false")
        if record.get("guest_installer_execution") is not True:
            found.append(f"{name} has guest_installer_execution false")
        if marker is not None and marker not in tail:
            found.append(f"{name} never showed {marker}")
        if installer_marker is not None and installer_marker not in tail:
            found.append(f"{name} never showed {installer_marker}")

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a finalized WSM Minimal Live release bundle before upload."
    )
    parser.add_argument("directory", help="directory with finalized release assets")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="inspect metadata while the whole ISO is absent; this never returns READY",
    )
    arguments = parser.parse_args(argv)

    found = problems(Path(arguments.directory), metadata_only=arguments.metadata_only)
    if found:
        print("\n".join(f"release-readiness: {item}" for item in found), file=sys.stderr)
        return 1
    if arguments.metadata_only:
        print("release-readiness: metadata checks passed; artifact not accepted (NOT_READY)")
        return 2
    print("release-readiness: complete evidence bundle verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
