#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a deterministic source bundle from a Git commit plus checksums."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
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

    prefix = f"wsm-desktop-{version}/"
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", f"--prefix={prefix}", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout

    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wb", compresslevel=9, mtime=0) as stream:
        stream.write(archive)

    tarball_digest = sha256_file(output)
    sums = output.with_name("SHA256SUMS")
    sums.write_text(f"{tarball_digest}  {output.name}\n", encoding="utf-8")

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
    manifest_path = output.with_name("release-manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


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
