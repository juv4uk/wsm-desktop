#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a deterministic source bundle from a Git commit plus checksums."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE_INFO = ROOT / "RELEASE-INFO.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _absolute_without_symlinks(path: Path) -> Path:
    """Normalize a path and reject every existing symlink component."""
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SystemExit(f"build-release-bundle: cannot inspect path component {current}: {exc}")
        if stat.S_ISLNK(info.st_mode):
            raise SystemExit(f"build-release-bundle: symlink path components are not allowed: {current}")
    return absolute


def _prepare_artifact_paths(version: str, requested: Path) -> tuple[Path, Path, Path]:
    """Validate a fresh output location before creating any release artifact."""
    expected_name = f"wsm-desktop-{version}-source.tar.gz"
    requested = requested.expanduser()
    if requested.name != expected_name:
        raise SystemExit(
            f"build-release-bundle: --output filename must be exactly {expected_name!r}"
        )

    parent = _absolute_without_symlinks(requested.parent)
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot create output directory: {exc}")
    parent = _absolute_without_symlinks(parent)
    try:
        real_parent = parent.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot resolve output directory: {exc}")
    if not real_parent.is_dir():
        raise SystemExit("build-release-bundle: output parent must be a directory")

    repository = ROOT.resolve()
    build_directory = repository / "build"
    if real_parent == repository or repository in real_parent.parents:
        if real_parent != build_directory and build_directory not in real_parent.parents:
            raise SystemExit(
                "build-release-bundle: output inside the repository is allowed only under build/"
            )

    output = real_parent / expected_name
    sums = real_parent / "SHA256SUMS"
    manifest = real_parent / "release-manifest.json"
    for path in (output, sums, manifest):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SystemExit(f"build-release-bundle: cannot inspect artifact path {path.name}: {exc}")
        raise SystemExit(
            f"build-release-bundle: refusing to overwrite existing artifact {path.name!r}"
        )
    return output, sums, manifest


def _open_new_file(path: Path, created: list[Path]):
    """Create a private file without following or replacing an existing path."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise SystemExit(
            f"build-release-bundle: refusing to overwrite existing artifact {path.name!r}"
        ) from exc
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot create {path.name}: {exc}") from exc
    created.append(path)
    return os.fdopen(descriptor, "wb")


def build(version: str, output: Path) -> dict[str, Any]:
    release = load_release()
    if version != release["version"]:
        raise SystemExit(
            f"build-release-bundle: requested {version}, RELEASE-INFO.json says {release['version']}"
        )

    commit = git_output(["rev-parse", "HEAD"])
    dirty = git_output(["status", "--porcelain"])
    if dirty:
        raise SystemExit("build-release-bundle: working tree must be clean before bundling")

    output, sums, manifest_path = _prepare_artifact_paths(version, output)
    prefix = f"wsm-desktop-{version}/"
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", f"--prefix={prefix}", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout

    created: list[Path] = []
    try:
        # O_EXCL + O_NOFOLLOW prevent clobbering tracked files or following a
        # symlink supplied as the tarball or one of its sibling artifacts.
        with _open_new_file(output, created) as raw:
            # GzipFile keeps the release reproducible on the Python >= 3.10 baseline.
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=0,
            ) as stream:
                stream.write(archive)

        tarball_digest = sha256_file(output)
        sums_bytes = f"{tarball_digest}  {output.name}\n".encode("utf-8")
        with _open_new_file(sums, created) as stream:
            stream.write(sums_bytes)

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
                output.name: {
                    "sha256": tarball_digest,
                    "bytes": output.stat().st_size,
                },
                sums.name: {
                    "sha256": sha256_file(sums),
                    "bytes": sums.stat().st_size,
                },
            },
        }
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with _open_new_file(manifest_path, created) as stream:
            stream.write(manifest_bytes)
        return manifest
    except BaseException:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=load_release()["version"])
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / f"wsm-desktop-{load_release()['version']}-source.tar.gz",
    )
    args = parser.parse_args(argv)
    manifest = build(args.version, args.output)
    print(f"bundle: {args.output}")
    print(f"sha256: {manifest['artifacts'][args.output.name]['sha256']}")
    print(f"commit: {manifest['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())