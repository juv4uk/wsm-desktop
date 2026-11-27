#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Build an exact SLSA subject list for whole or split Minimal Live ISO assets."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REQUIRED_ASSETS = (
    "SHA256SUMS",
    "build-manifest.json",
    "release-manifest.json",
    "boot-bios.json",
    "boot-uefi.json",
)
_PART_NAME = re.compile(r"^.+\.iso\.part[0-9]{3}$")


class SubjectListError(ValueError):
    """The release directory does not contain one valid published image form."""


def _require_nonempty_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise SubjectListError(f"required release subject is not a regular file: {path.name}")
    if path.stat().st_size <= 0:
        raise SubjectListError(f"required release subject is empty: {path.name}")


def build_subject_paths(release_dir: Path, iso_name: str) -> list[Path]:
    """Return the exact files to attest for either a whole ISO or split ISO."""
    if Path(iso_name).name != iso_name or not iso_name.endswith(".iso"):
        raise SubjectListError("ISO name must be a plain .iso filename")

    root = release_dir.resolve(strict=True)
    if not root.is_dir():
        raise SubjectListError(f"release directory is not a directory: {root}")

    whole = root / iso_name
    parts = sorted(root.glob(f"{iso_name}.part*"), key=lambda path: path.name)
    sidecar = root / "ISO-CHECKSUMS.sha256"

    if whole.exists():
        if whole.is_symlink() or not whole.is_file():
            raise SubjectListError(f"whole ISO is not a regular file: {whole.name}")
        if parts or sidecar.exists():
            raise SubjectListError("whole ISO cannot coexist with split parts or ISO checksum sidecar")
        image_subjects = [whole]
    else:
        if not parts:
            raise SubjectListError("neither a whole ISO nor split ISO parts were found")
        if not sidecar.exists():
            raise SubjectListError("split ISO parts require ISO-CHECKSUMS.sha256")
        for part in parts:
            if not _PART_NAME.fullmatch(part.name):
                raise SubjectListError(f"unexpected split part name: {part.name}")
            _require_nonempty_regular_file(part)
        _require_nonempty_regular_file(sidecar)
        image_subjects = [*parts, sidecar]

    required = [root / name for name in _REQUIRED_ASSETS]
    for path in [*image_subjects, *required]:
        _require_nonempty_regular_file(path)

    return [path.resolve(strict=True) for path in [*image_subjects, *required]]


def write_github_outputs(subjects: list[Path], subject_file: Path, github_output: Path) -> None:
    """Write the newline-delimited subject file and GitHub step outputs."""
    subject_file.parent.mkdir(parents=True, exist_ok=True)
    subject_file.write_text("".join(f"{path}\n" for path in subjects), encoding="utf-8")

    delimiter = "WSM_ATTESTATION_SUBJECTS"
    with github_output.open("a", encoding="utf-8") as handle:
        handle.write(f"paths<<{delimiter}\n")
        handle.write("".join(f"{path}\n" for path in subjects))
        handle.write(f"{delimiter}\n")
        handle.write(f"subject_count={len(subjects)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--iso-name", required=True)
    parser.add_argument("--subject-file", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        subjects = build_subject_paths(args.release_dir, args.iso_name)
        write_github_outputs(subjects, args.subject_file, args.github_output)
    except (OSError, SubjectListError) as error:
        print(f"RELEASE-ATTESTATION-SUBJECTS-FAIL: {error}", file=sys.stderr)
        return 1

    print(f"RELEASE-ATTESTATION-SUBJECTS-OK count={len(subjects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
