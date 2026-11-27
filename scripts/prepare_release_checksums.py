#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Prepare the exact checksum/manifest set published by Minimal Live Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class ReleaseManifestError(ValueError):
    """The release directory does not match its declared ISO form."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(root: Path, name: str) -> Path:
    path = root / name
    if not SAFE_NAME.fullmatch(name) or path.name != name:
        raise ReleaseManifestError(f"unsafe asset name: {name!r}")
    if not path.is_file() or path.is_symlink():
        raise ReleaseManifestError(f"missing or non-regular release asset: {name}")
    return path


def _combined_sha256(paths: list[Path]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for path in paths:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    return digest.hexdigest(), size


def prepare_release_checksums(
    release_dir: Path,
    iso_name: str,
    published_as: str,
) -> dict[str, object]:
    """Write release-manifest.json, ISO-CHECKSUMS.sha256 and top-level SHA256SUMS.

    The sidecar exists for both forms: it covers the whole ISO in whole-file
    mode, or every ordered part in split mode. SHA256SUMS covers the sidecar
    itself, so the uploaded/attested asset set is identical in both modes.
    """
    if published_as not in {"whole", "parts"}:
        raise ReleaseManifestError(f"unsupported published form: {published_as!r}")
    if not SAFE_NAME.fullmatch(iso_name):
        raise ReleaseManifestError(f"unsafe ISO name: {iso_name!r}")

    root = release_dir.resolve(strict=True)
    if not root.is_dir():
        raise ReleaseManifestError(f"release path is not a directory: {root}")

    manifest_path = _regular_file(root, "release-manifest.json")
    build_manifest = _regular_file(root, "build-manifest.json")
    bios = _regular_file(root, "boot-bios.json")
    uefi = _regular_file(root, "boot-uefi.json")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError(f"cannot read release manifest: {exc}") from exc
    artifact = manifest.get("artifact") if isinstance(manifest, dict) else None
    if not isinstance(artifact, dict):
        raise ReleaseManifestError("release manifest has no artifact object")
    expected_sha = artifact.get("sha256")
    expected_bytes = artifact.get("bytes")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ReleaseManifestError("release manifest has no valid artifact SHA-256")
    if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes < 1:
        raise ReleaseManifestError("release manifest has no valid artifact byte size")

    iso_path = root / iso_name
    part_paths = sorted(root.glob(iso_name + ".part*"), key=lambda path: path.name)
    if any(path.is_symlink() or not path.is_file() for path in part_paths):
        raise ReleaseManifestError("split ISO contains a symlink or non-regular part")

    if published_as == "whole":
        if part_paths:
            raise ReleaseManifestError("whole ISO mode must not contain stale split parts")
        iso_path = _regular_file(root, iso_name)
        actual_sha = sha256_file(iso_path)
        actual_bytes = iso_path.stat().st_size
        if actual_sha != expected_sha or actual_bytes != expected_bytes:
            raise ReleaseManifestError("whole ISO does not match release-manifest.json")
        artifact["published_as"] = "whole"
        artifact.pop("parts", None)
        artifact.pop("parts_count", None)
        artifact.pop("note", None)
        iso_assets = [iso_path]
    else:
        if iso_path.exists():
            raise ReleaseManifestError("split ISO mode must not contain the unsplit ISO")
        if len(part_paths) < 2:
            raise ReleaseManifestError("split ISO mode requires at least two parts")
        actual_sha, actual_bytes = _combined_sha256(part_paths)
        if actual_sha != expected_sha or actual_bytes != expected_bytes:
            raise ReleaseManifestError("ordered split parts do not reconstruct the declared ISO")
        parts = [path.name for path in part_paths]
        artifact["published_as"] = "parts"
        artifact["parts"] = parts
        artifact["parts_count"] = len(parts)
        artifact["note"] = (
            "Concatenate the parts in lexical order to obtain the ISO whose "
            "size and SHA-256 are recorded in this manifest."
        )
        iso_assets = part_paths

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sidecar = root / "ISO-CHECKSUMS.sha256"
    sidecar_lines = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in iso_assets
    )
    sidecar.write_text(sidecar_lines, encoding="utf-8")

    covered = iso_assets + [build_manifest, manifest_path, bios, uefi, sidecar]
    sums = "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in covered
    )
    (root / "SHA256SUMS").write_text(sums, encoding="utf-8")

    # Re-read the just-written manifest and verify every entry before upload.
    for line in sums.splitlines():
        digest, name = line.split("  ", 1)
        if sha256_file(_regular_file(root, name)) != digest:
            raise ReleaseManifestError(f"checksum self-check failed for {name}")

    return {
        "published_as": published_as,
        "asset_count": len(covered),
        "iso_assets": [path.name for path in iso_assets],
        "sidecar": sidecar.name,
        "sidecar_sha256": sha256_file(sidecar),
        "sha256sums_sha256": sha256_file(root / "SHA256SUMS"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("iso_name")
    parser.add_argument("release_parts", choices=("0", "1"))
    args = parser.parse_args(argv)
    published_as = "parts" if args.release_parts == "1" else "whole"
    try:
        result = prepare_release_checksums(args.release_dir, args.iso_name, published_as)
    except (OSError, ReleaseManifestError) as exc:
        print(f"prepare-release-checksums: {exc}", file=sys.stderr)
        return 1
    print(
        "RELEASE-CHECKSUMS-READY "
        f"published_as={result['published_as']} "
        f"assets={result['asset_count']} "
        f"sidecar={result['sidecar']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
