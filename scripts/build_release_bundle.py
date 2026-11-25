#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a deterministic source bundle without overwriting existing paths."""

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
from typing import Any, Callable, TextIO

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


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinks in every existing component, including dangling links."""
    for component in reversed(path.parents):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SystemExit(f"build-release-bundle: cannot inspect {component}: {exc}")
        if stat.S_ISLNK(metadata.st_mode):
            raise SystemExit(f"build-release-bundle: symlink path component is not allowed: {component}")


def _prepare_destinations(output: Path) -> tuple[Path, Path, Path]:
    output = Path(os.path.abspath(output.expanduser()))
    sums = output.with_name("SHA256SUMS")
    manifest = output.with_name("release-manifest.json")
    destinations = (output, sums, manifest)

    if len(set(destinations)) != len(destinations):
        raise SystemExit("build-release-bundle: artifact paths collide")
    if output == ROOT or ROOT in output.parents:
        raise SystemExit("build-release-bundle: output must be outside the repository tree")

    for path in destinations:
        _reject_symlink_components(path)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise SystemExit(f"build-release-bundle: cannot inspect destination {path}: {exc}")
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise SystemExit(f"build-release-bundle: symlink destination is not allowed: {path}")
            raise SystemExit(f"build-release-bundle: destination already exists: {path}")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"build-release-bundle: cannot create output directory: {exc}")

    _reject_symlink_components(output)
    if not output.parent.is_dir():
        raise SystemExit("build-release-bundle: output parent is not a directory")
    for path in destinations:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SystemExit(f"build-release-bundle: cannot inspect destination {path}: {exc}")
        raise SystemExit(f"build-release-bundle: destination already exists: {path}")

    return output, sums, manifest


def _write_exclusive(path: Path, writer: Callable[[Any], None], created: list[Path]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    created.append(path)
    with os.fdopen(descriptor, "wb") as stream:
        writer(stream)


def _remove_created(paths: list[Path]) -> None:
    for path in reversed(paths):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # Never replace the original build error with a cleanup error.
            pass


def build(version: str, output: Path) -> dict[str, Any]:
    release = load_release()
    if version != release["version"]:
        raise SystemExit(
            f"build-release-bundle: requested {version}, RELEASE-INFO.json says {release['version']}"
        )

    output, sums, manifest_path = _prepare_destinations(output)
    commit = git_output(["rev-parse", "HEAD"])
    dirty = git_output(["status", "--porcelain"])
    if dirty:
        raise SystemExit("build-release-bundle: working tree must be clean before bundling")

    prefix = f"wsm-desktop-{version}/"
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", f"--prefix={prefix}", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout

    created: list[Path] = []
    try:
        def write_archive(raw: Any) -> None:
            # GzipFile keeps deterministic output on the documented Python >= 3.10 baseline.
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=0,
            ) as stream:
                stream.write(archive)

        _write_exclusive(output, write_archive, created)
        tarball_digest = sha256_file(output)
        sums_bytes = f"{tarball_digest}  {output.name}\n".encode("utf-8")
        _write_exclusive(sums, lambda stream: stream.write(sums_bytes), created)

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
        _write_exclusive(manifest_path, lambda stream: stream.write(manifest_bytes), created)
        return manifest
    except OSError as exc:
        _remove_created(created)
        raise SystemExit(f"build-release-bundle: failed to create release artifacts: {exc}")
    except BaseException:
        _remove_created(created)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=load_release()["version"])
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT.parent / "build" / f"wsm-desktop-{load_release()['version']}-source.tar.gz",
    )
    args = parser.parse_args(argv)
    manifest = build(args.version, args.output)
    print(f"bundle: {args.output}")
    print(f"sha256: {manifest['artifacts'][args.output.name]['sha256']}")
    print(f"commit: {manifest['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
