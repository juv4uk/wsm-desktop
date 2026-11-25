#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a deterministic source bundle without overwriting existing files."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE_INFO = ROOT / "RELEASE-INFO.json"
SUMS_NAME = "SHA256SUMS"
MANIFEST_NAME = "release-manifest.json"


def git_output(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def load_release() -> dict[str, Any]:
    try:
        value = json.loads(RELEASE_INFO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"build-release-bundle: cannot read {RELEASE_INFO}: {exc}")
    if not isinstance(value, dict) or "version" not in value:
        raise SystemExit(f"build-release-bundle: invalid {RELEASE_INFO}")
    return value


def _safe_output_parent(parent: Path) -> Path:
    """Create a non-symlink output directory outside the repository tree."""
    requested = parent.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if ".." in requested.parts:
        raise SystemExit("build-release-bundle: output path must not contain '..'")

    current = Path(requested.anchor)
    for component in requested.parts[1:]:
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
                metadata = current.lstat()
            except OSError as exc:
                raise SystemExit(
                    f"build-release-bundle: cannot create output directory {current}: {exc}"
                ) from exc
        except OSError as exc:
            raise SystemExit(
                f"build-release-bundle: cannot inspect output directory {current}: {exc}"
            ) from exc

        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(
                f"build-release-bundle: output directory contains a symlink: {current}"
            )
        if not stat.S_ISDIR(metadata.st_mode):
            raise SystemExit(
                f"build-release-bundle: output parent component is not a directory: {current}"
            )

    resolved = current.resolve(strict=True)
    repository = ROOT.resolve()
    try:
        resolved.relative_to(repository)
    except ValueError:
        pass
    else:
        raise SystemExit(
            "build-release-bundle: output directory must be outside the repository tree"
        )

    for special in (Path("/dev"), Path("/proc"), Path("/sys")):
        if resolved == special or special in resolved.parents:
            raise SystemExit(
                f"build-release-bundle: output directory must not be under {special}"
            )
    return resolved


def _require_absent(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot inspect artifact path {path}: {exc}") from exc
    raise SystemExit(
        f"build-release-bundle: refusing to overwrite existing artifact: {path}"
    )


def _write_new_file(path: Path, payload: bytes) -> None:
    """Create a new regular file with exclusive/no-follow semantics."""
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise SystemExit(
            f"build-release-bundle: refusing to overwrite existing artifact: {path}"
        ) from exc
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot create artifact {path}: {exc}") from exc

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot write artifact {path}: {exc}") from exc


def build(version: str, output: Path) -> dict[str, Any]:
    release = load_release()
    if version != release["version"]:
        raise SystemExit(
            f"build-release-bundle: requested {version}, RELEASE-INFO.json says {release['version']}"
        )

    canonical_name = f"wsm-desktop-{version}-source.tar.gz"
    if output.name != canonical_name:
        raise SystemExit(
            f"build-release-bundle: output must be named {canonical_name!r}; "
            f"SHA256SUMS would otherwise name {output.name!r}, which is not the "
            "published asset and breaks `sha256sum -c SHA256SUMS`"
        )

    commit = git_output(["rev-parse", "HEAD"])
    dirty = git_output(["status", "--porcelain"])
    if dirty:
        raise SystemExit("build-release-bundle: working tree must be clean before bundling")

    output_parent = _safe_output_parent(output.parent)
    output_path = output_parent / canonical_name
    sums_path = output_parent / SUMS_NAME
    manifest_path = output_parent / MANIFEST_NAME
    for artifact_path in (output_path, sums_path, manifest_path):
        _require_absent(artifact_path)

    prefix = f"wsm-desktop-{version}/"
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", f"--prefix={prefix}", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout

    compressed = io.BytesIO()
    # GzipFile with mtime=0 keeps the archive stable on the same platform and
    # compression implementation; the release manifest records the exact source commit.
    with gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=9,
        fileobj=compressed,
        mtime=0,
    ) as stream:
        stream.write(archive)
    tarball_bytes = compressed.getvalue()
    tarball_digest = hashlib.sha256(tarball_bytes).hexdigest()

    _write_new_file(output_path, tarball_bytes)
    sums_bytes = f"{tarball_digest}  {canonical_name}\n".encode("utf-8")
    _write_new_file(sums_path, sums_bytes)

    manifest = {
        "schema": "wsm-release-manifest/1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release": release,
        "source_commit": commit,
        "build": {
            "command": "git archive --format=tar HEAD | gzip -n -9",
            "gzip_mtime": 0,
            "prefix": prefix,
        },
        "artifacts": {
            canonical_name: {
                "sha256": tarball_digest,
                "bytes": len(tarball_bytes),
            },
            SUMS_NAME: {
                "sha256": hashlib.sha256(sums_bytes).hexdigest(),
                "bytes": len(sums_bytes),
            },
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_new_file(manifest_path, manifest_bytes)
    return manifest


def main(argv: list[str] | None = None) -> int:
    release = load_release()
    version = release["version"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=version)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT.parent / f"{ROOT.name}-release" / f"wsm-desktop-{version}-source.tar.gz",
        help="destination using the canonical source-tarball filename; parent directory is created safely",
    )
    args = parser.parse_args(argv)
    manifest = build(args.version, args.output)
    print(f"bundle: {args.output}")
    print(f"sha256: {manifest['artifacts'][args.output.name]['sha256']}")
    print(f"commit: {manifest['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
