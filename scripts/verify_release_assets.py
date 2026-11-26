# SPDX-License-Identifier: LicenseRef-Volnist
"""Verify GitHub release assets after downloading them back from the release.

The release remains a draft until this check proves that the exact expected
asset set arrived intact. This is stricter than sha256sum -c: it also rejects
missing/extra files, symlinks, duplicate entries and paths outside the bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path


class ReleaseAssetError(ValueError):
    """The downloaded release bundle differs from the local bundle."""


SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")


def _regular_file(directory: Path, name: str) -> Path:
    path = directory / name
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ReleaseAssetError(f"missing asset {name!r} in {directory}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise ReleaseAssetError(f"asset is not a regular file: {path}")
    return path


def _safe_asset_name(name: str) -> None:
    if (
        not name
        or name in {".", "..", "SHA256SUMS"}
        or "/" in name
        or chr(92) in name
        or Path(name).name != name
    ):
        raise ReleaseAssetError(f"unsafe or reserved asset name in SHA256SUMS: {name!r}")


def parse_checksums(path: Path) -> dict[str, str]:
    """Parse strict sha256sum output; ambiguous lines are a failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseAssetError(f"cannot read SHA256SUMS: {exc}") from exc

    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        match = SUM_LINE.fullmatch(line)
        if match is None:
            raise ReleaseAssetError(f"invalid SHA256SUMS line {number}")
        digest, name = match.groups()
        _safe_asset_name(name)
        if name in entries:
            raise ReleaseAssetError(f"duplicate SHA256SUMS entry: {name}")
        entries[name] = digest.lower()
    if not entries:
        raise ReleaseAssetError("SHA256SUMS contains no assets")
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_files(directory: Path) -> set[str]:
    if not directory.is_dir():
        raise ReleaseAssetError(f"asset directory does not exist: {directory}")
    names: set[str] = set()
    for item in directory.iterdir():
        if not stat.S_ISREG(item.lstat().st_mode):
            raise ReleaseAssetError(f"non-regular entry in asset directory: {item.name}")
        names.add(item.name)
    return names


def verify_release_assets(expected_dir: Path, downloaded_dir: Path) -> dict[str, object]:
    """Verify exact remote file set and bytes against the local release bundle."""
    expected_dir = expected_dir.resolve(strict=True)
    downloaded_dir = downloaded_dir.resolve(strict=True)

    local_sums = _regular_file(expected_dir, "SHA256SUMS")
    remote_sums = _regular_file(downloaded_dir, "SHA256SUMS")
    local_sums_bytes = local_sums.read_bytes()
    remote_sums_bytes = remote_sums.read_bytes()
    if local_sums_bytes != remote_sums_bytes:
        raise ReleaseAssetError("downloaded SHA256SUMS differs from the local checksum manifest")

    entries = parse_checksums(local_sums)
    expected_names = set(entries) | {"SHA256SUMS"}
    actual_names = _directory_files(downloaded_dir)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ReleaseAssetError(f"downloaded asset set differs: missing={missing}, extra={extra}")

    verified: list[dict[str, str]] = []
    for name, expected_digest in sorted(entries.items()):
        local_path = _regular_file(expected_dir, name)
        remote_path = _regular_file(downloaded_dir, name)
        local_digest = sha256(local_path)
        remote_digest = sha256(remote_path)
        if local_digest != expected_digest:
            raise ReleaseAssetError(
                f"local asset {name} no longer matches SHA256SUMS: {local_digest}"
            )
        if remote_digest != expected_digest:
            raise ReleaseAssetError(
                f"downloaded asset {name} checksum mismatch: expected {expected_digest}, got {remote_digest}"
            )
        verified.append({"name": name, "sha256": remote_digest})

    return {
        "schema": "wsm-release-assets-verification/1",
        "status": "pass",
        "verified_asset_count": len(verified),
        "sha256sums_sha256": hashlib.sha256(remote_sums_bytes).hexdigest(),
        "assets": verified,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify-release-assets",
        description="Verify the exact asset set downloaded back from a draft GitHub release.",
    )
    parser.add_argument("--expected-dir", required=True, type=Path)
    parser.add_argument("--downloaded-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="write the verification report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_release_assets(args.expected_dir, args.downloaded_dir)
    except (OSError, ReleaseAssetError) as exc:
        print(f"verify-release-assets: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
