# SPDX-License-Identifier: LicenseRef-Volnist
"""Repository scanner for hardware profile evidence.

All semantic and artifact-byte checks are delegated to wsm_install.profile so
the installer and this command cannot drift into different definitions of
valid evidence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "profiles" / "hardware"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.profile import (  # noqa: E402
    EvidenceUnavailable,
    load,
    problems as profile_problems,
    slug_matches_directory,
)


def validate(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
) -> list[str]:
    """Use the installer's shared validator, including actual artifact bytes."""
    try:
        return profile_problems(document, schema, artifact_root=artifact_root)
    except EvidenceUnavailable as exc:
        return [str(exc)]


def validate_directory(path: Path, profiles_dir: Path = PROFILES_DIR) -> list[str]:
    """Validate evidence, artifacts and canonical vendor/model slug."""
    if path.is_symlink():
        return ["evidence.json must not be a symbolic link"]
    if path.parent.is_symlink():
        return ["profile directory must not be a symbolic link"]
    if not (path.parent / "profile.scm").is_file():
        return ["profile directory has no profile.scm"]

    try:
        document = load(path)
    except EvidenceUnavailable as exc:
        return [str(exc)]

    problems = validate(document, artifact_root=path.parent)
    if problems:
        return problems
    return slug_matches_directory(document, path.parent, profiles_dir)


def discover_profile_directories(profiles_dir: Path) -> tuple[list[Path], list[str]]:
    """Discover every vendor/model directory and reject symlink directories."""
    directories: list[Path] = []
    problems: list[str] = []
    try:
        vendors = sorted(profiles_dir.iterdir())
    except OSError as exc:
        return [], [f"cannot list profiles directory: {exc}"]

    for vendor in vendors:
        if vendor.name.startswith(".") or not vendor.is_dir():
            continue
        if vendor.is_symlink():
            problems.append(f"vendor directory must not be a symbolic link: {vendor}")
            continue
        try:
            models = sorted(vendor.iterdir())
        except OSError as exc:
            problems.append(f"cannot list vendor directory {vendor}: {exc}")
            continue
        for model in models:
            if model.name.startswith(".") or not model.is_dir():
                continue
            if model.is_symlink():
                problems.append(f"model directory must not be a symbolic link: {model}")
                continue
            profile_file = model / "profile.scm"
            evidence_file = model / "evidence.json"
            # A README-only research reference is not a declared hardware profile.
            # Once either profile marker exists (including a dangling symlink),
            # require the complete profile/evidence pair below.
            if not any(
                path.exists() or path.is_symlink()
                for path in (profile_file, evidence_file)
            ):
                continue
            directories.append(model)
    return directories, problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-profile-evidence",
        description="Validate hardware profile evidence bundles.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--file",
        type=Path,
        help="validate one evidence.json and artifacts relative to its directory",
    )
    selection.add_argument(
        "--dir",
        type=Path,
        default=PROFILES_DIR,
        help="scan <vendor>/<model> directories for profile.scm and evidence.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        target = args.file
        try:
            document = load(target)
            problems = validate(document, artifact_root=target.parent)
        except EvidenceUnavailable as exc:
            problems = [str(exc)]
        if problems:
            print(f"{target}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"{target}: schema and artifact checks passed (directory slug not checked)")
        return 0

    profiles_dir = args.dir
    if profiles_dir.is_symlink() or not profiles_dir.is_dir():
        print(
            f"check-profile-evidence: profiles directory not found or is a symbolic link: {profiles_dir}",
            file=sys.stderr,
        )
        return 2

    directories, discovery_problems = discover_profile_directories(profiles_dir)
    failures = len(discovery_problems)
    for problem in discovery_problems:
        print(f"  - {problem}", file=sys.stderr)

    if not directories and not failures:
        print("check-profile-evidence: no hardware profile directories yet")
        return 0

    accepted = 0
    for model_dir in directories:
        profile_file = model_dir / "profile.scm"
        evidence_file = model_dir / "evidence.json"
        problems: list[str] = []
        if profile_file.is_symlink() or not profile_file.is_file():
            problems.append("missing mandatory profile.scm; this directory is not a complete profile")
        if evidence_file.is_symlink() or not evidence_file.is_file():
            problems.append("missing mandatory evidence.json; this directory is not a verified profile")
        if not problems:
            problems = validate_directory(evidence_file, profiles_dir)

        if problems:
            failures += 1
            print(f"{model_dir}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            accepted += 1
            print(f"{evidence_file}: ok")

    if failures:
        print(
            f"check-profile-evidence: {failures} problem(s), {accepted} bundle(s) accepted",
            file=sys.stderr,
        )
        return 1

    print(f"check-profile-evidence: {accepted} bundle(s) accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
