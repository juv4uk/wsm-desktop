# SPDX-License-Identifier: LicenseRef-Volnist
"""Fail-closed validation of a complete WSM Minimal Live release bundle.

The checker runs after the workflow has finalized the manifest and SHA256SUMS,
including the whole-ISO or multipart publication representation. An empty
problem list means the shipped evidence supports the release claims.
"""

from __future__ import annotations

import argparse
import base64
import binascii
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
    "build.log",
    "release-manifest.json",
    "boot-bios.json",
    "boot-uefi.json",
    "channels.resolved.scm",
    "channel-resolution.log",
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


def channel_resolution_log_problems(directory: Path) -> list[str]:
    """Validate the Guix transcript, not merely the existence of a log file."""
    path = directory / "channel-resolution.log"
    channels_path = directory / "channels.resolved.scm"
    try:
        document = read_json_object(path)
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid channel-resolution.log JSON: {error}"]

    found: list[str] = []
    if document.get("schema") != "wsm-channel-resolution/1":
        found.append("channel-resolution.log has an unsupported schema")
    if document.get("launch_error") is not None:
        found.append("channel-resolution.log records a Guix launch error")

    command = document.get("command")
    if (
        not isinstance(command, list)
        or len(command) != 10
        or not all(isinstance(part, str) for part in command)
    ):
        found.append("channel-resolution.log command is missing or malformed")
    else:
        if (
            not Path(command[0]).is_absolute()
            or Path(command[0]).name != "guix"
            or command[1:3] != ["time-machine", "-C"]
            or not Path(command[3]).is_absolute()
            or command[4] != "-L"
            or not Path(command[5]).is_absolute()
            or command[6:] != ["--", "describe", "-f", "channels"]
            or "--disable-authentication" in command
        ):
            found.append("channel-resolution.log does not record the expected locked Guix describe command")

    status = document.get("exit_status")
    if not isinstance(status, int) or isinstance(status, bool) or status != 0:
        found.append("channel-resolution.log does not record a successful exit status")

    stdout = document.get("stdout")
    if not isinstance(stdout, dict):
        found.append("channel-resolution.log stdout evidence is missing or invalid")
    else:
        if stdout.get("file") != "channels.resolved.scm":
            found.append("channel-resolution.log stdout file is not channels.resolved.scm")
        try:
            channels_bytes = channels_path.read_bytes()
        except OSError as error:
            found.append(f"cannot read channels.resolved.scm for transcript validation: {error}")
        else:
            if b"channel authentication disabled" in channels_bytes.lower():
                found.append("channels.resolved.scm reports disabled channel authentication")
            stdout_bytes = stdout.get("bytes")
            if (
                not isinstance(stdout_bytes, int)
                or isinstance(stdout_bytes, bool)
                or stdout_bytes <= 0
                or stdout_bytes != len(channels_bytes)
            ):
                found.append("channel-resolution.log stdout byte count does not match channels.resolved.scm")
            stdout_digest = stdout.get("sha256")
            if (
                not isinstance(stdout_digest, str)
                or SHA256.fullmatch(stdout_digest) is None
                or stdout_digest != hashlib.sha256(channels_bytes).hexdigest()
            ):
                found.append("channel-resolution.log stdout digest does not match channels.resolved.scm")

    stderr = document.get("stderr")
    if not isinstance(stderr, dict):
        found.append("channel-resolution.log stderr evidence is missing or invalid")
    else:
        encoded = stderr.get("base64")
        stderr_text = stderr.get("text")
        stderr_bytes = stderr.get("bytes")
        stderr_digest = stderr.get("sha256")
        try:
            if not isinstance(encoded, str):
                raise ValueError("base64 value is not a string")
            raw_stderr = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError, TypeError):
            found.append("channel-resolution.log stderr base64 is malformed")
        else:
            if (
                not isinstance(stderr_bytes, int)
                or isinstance(stderr_bytes, bool)
                or stderr_bytes < 0
                or stderr_bytes != len(raw_stderr)
            ):
                found.append("channel-resolution.log stderr byte count is inconsistent")
            if (
                not isinstance(stderr_digest, str)
                or SHA256.fullmatch(stderr_digest) is None
                or stderr_digest != hashlib.sha256(raw_stderr).hexdigest()
            ):
                found.append("channel-resolution.log stderr digest is inconsistent")
            if (
                not isinstance(stderr_text, str)
                or stderr_text != raw_stderr.decode("utf-8", errors="replace")
            ):
                found.append("channel-resolution.log stderr text does not match captured bytes")
            if b"channel authentication disabled" in raw_stderr.lower():
                found.append("channel-resolution.log reports disabled channel authentication")

    return found


def problems(directory: Path, metadata_only: bool = False) -> list[str]:
    """Return every reason the final release bundle is not ready."""
    if directory.is_symlink():
        return ["release bundle directory must not be a symlink"]

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
        build_manifest = read_json_object(directory / "build-manifest.json")
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid release metadata: {error}"]

    guix = build_manifest.get("guix")
    if not isinstance(guix, dict):
        found.append("build-manifest guix section is missing or invalid")
        guix = {}

    channel_evidence = (
        (
            "resolved_channels_file",
            "channels.resolved.scm",
            "resolved_channels_sha256",
            "resolved_channels_bytes",
            True,
        ),
        (
            "channel_resolution_log",
            "channel-resolution.log",
            "channel_resolution_log_sha256",
            "channel_resolution_log_bytes",
            True,
        ),
    )
    build_section = build_manifest.get("build")
    if not isinstance(build_section, dict):
        found.append("build-manifest build section is missing or invalid")
        build_section = {}
    build_log_name = build_section.get("log")
    if build_log_name != "build.log":
        found.append("build-manifest build.log must be build.log")
    build_log_sha = build_section.get("log_sha256")
    if not isinstance(build_log_sha, str) or SHA256.fullmatch(build_log_sha) is None:
        found.append("build-manifest build.log_sha256 is missing or malformed")
    else:
        if sums.get("build.log") != build_log_sha:
            found.append("build-manifest build.log_sha256 != SHA256SUMS entry for build.log")
        if (directory / "build.log").is_file() and sha256_of(directory / "build.log") != build_log_sha:
            found.append("build.log does not match build-manifest build.log_sha256")
    build_log_bytes = build_section.get("log_bytes")
    if (
        not isinstance(build_log_bytes, int)
        or isinstance(build_log_bytes, bool)
        or build_log_bytes <= 0
    ):
        found.append("build-manifest build.log_bytes is missing or invalid")
    elif (directory / "build.log").is_file() and (directory / "build.log").stat().st_size != build_log_bytes:
        found.append("build.log does not match build-manifest build.log_bytes")

    for filename_key, expected_name, digest_key, bytes_key, must_be_nonempty in channel_evidence:
        recorded_name = guix.get(filename_key)
        if recorded_name != expected_name:
            found.append(f"build-manifest guix.{filename_key} must be {expected_name}")
        recorded_digest = guix.get(digest_key)
        if not isinstance(recorded_digest, str) or SHA256.fullmatch(recorded_digest) is None:
            found.append(f"build-manifest guix.{digest_key} is missing or malformed")
        elif sums.get(expected_name) != recorded_digest:
            found.append(f"build-manifest guix.{digest_key} != SHA256SUMS entry for {expected_name}")
        recorded_bytes = guix.get(bytes_key)
        if (
            not isinstance(recorded_bytes, int)
            or isinstance(recorded_bytes, bool)
            or recorded_bytes < 0
            or (must_be_nonempty and recorded_bytes == 0)
        ):
            found.append(f"build-manifest guix.{bytes_key} is missing or invalid")
        else:
            actual_bytes = (directory / expected_name).stat().st_size
            if actual_bytes != recorded_bytes:
                found.append(
                    f"build-manifest guix.{bytes_key} {recorded_bytes} != actual bytes {actual_bytes}"
                )

    resolution_status = guix.get("channel_resolution_exit_status")
    if (
        not isinstance(resolution_status, int)
        or isinstance(resolution_status, bool)
        or resolution_status != 0
    ):
        found.append("channel resolution did not exit successfully")

    found.extend(channel_resolution_log_problems(directory))

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

    # Bind the builder's artifact and source to the release manifest. Hashing
    # both documents independently is insufficient if they describe different
    # images or different source commits.
    build_artifact = build_manifest.get("artifact")
    if not isinstance(build_artifact, dict):
        found.append("build-manifest artifact section is missing or invalid")
        build_artifact = {}

    build_filename = build_artifact.get("filename")
    if not isinstance(build_filename, str) or not build_filename:
        found.append("build-manifest artifact filename is missing or invalid")
    elif filename is not None and build_filename != filename:
        found.append(
            f"build-manifest artifact filename {build_filename!r} != release-manifest {filename!r}"
        )

    build_sha = build_artifact.get("sha256")
    if not isinstance(build_sha, str) or SHA256.fullmatch(build_sha) is None:
        found.append("build-manifest artifact sha256 is missing or malformed")
    elif artifact_sha is not None and build_sha != artifact_sha:
        found.append("build-manifest artifact sha256 != release-manifest artifact sha256")

    build_bytes = build_artifact.get("size_bytes")
    if not isinstance(build_bytes, int) or isinstance(build_bytes, bool) or build_bytes <= 0:
        found.append("build-manifest artifact size_bytes is missing or invalid")
    elif artifact_bytes is not None and build_bytes != artifact_bytes:
        found.append(
            f"build-manifest artifact size_bytes {build_bytes} != release-manifest artifact bytes {artifact_bytes}"
        )

    build_source = build_manifest.get("source")
    release_info = manifest.get("release")
    if not isinstance(build_source, dict):
        found.append("build-manifest source section is missing or invalid")
        build_source = {}
    if not isinstance(release_info, dict):
        found.append("release-manifest release section is missing or invalid")
        release_info = {}
    build_commit = build_source.get("commit")
    release_commit = release_info.get("source_commit")
    if not isinstance(build_commit, str) or not build_commit:
        found.append("build-manifest source.commit is missing or invalid")
    if not isinstance(release_commit, str) or not release_commit:
        found.append("release-manifest release.source_commit is missing or invalid")
    elif isinstance(build_commit, str) and build_commit and build_commit != release_commit:
        found.append("build-manifest source.commit != release-manifest release.source_commit")

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
                    f"{sha256_of(directory / part)}  {part}\n" for part in parts
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
        if record.get("serial_clean") is not True:
            found.append(f"{name} has serial_clean false or missing")
        failure_markers = record.get("serial_failure_markers")
        if (
            not isinstance(failure_markers, list)
            or any(not isinstance(marker, str) or not marker for marker in failure_markers)
        ):
            found.append(f"{name} serial_failure_markers is missing or malformed")
        elif failure_markers:
            found.append(f"{name} contains serial failure markers: {', '.join(failure_markers)}")
        boot_iso_sha = record.get("iso_sha256")
        if not isinstance(boot_iso_sha, str) or SHA256.fullmatch(boot_iso_sha) is None:
            found.append(f"{name} iso_sha256 is missing or malformed")
        elif artifact_sha is None or boot_iso_sha != artifact_sha:
            found.append(f"{name} boot evidence iso_sha256 != release-manifest artifact sha256")
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
