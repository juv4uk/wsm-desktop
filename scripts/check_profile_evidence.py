# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate hardware profile evidence bundles and their referenced artifacts.

A profile is a claim about a specific machine. It needs a valid evidence bundle,
and every artifact digest must resolve to bytes stored inside that profile.
The directory scanner also rejects profile.scm files without evidence.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "profile-evidence.schema.json"
PROFILES_DIR = ROOT / "profiles" / "hardware"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.profile import problems as profile_problems  # noqa: E402


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    artifact_root: Path | None = None,
) -> list[str]:
    """Reuse the installer's single semantic and artifact validator."""
    return profile_problems(document, schema, artifact_root=artifact_root)


def validate_directory(path: Path, root: Path = PROFILES_DIR) -> list[str]:
    """Validate evidence.json, its artifacts, and its vendor/model directory slug."""
    if path.is_symlink():
        return ["evidence.json must not be a symlink"]
    if path.parent.is_symlink():
        return ["profile directory must not be a symlink"]

    document, read_problems = read_document(path)
    if read_problems:
        return read_problems
    assert document is not None

    problems = validate(document, artifact_root=path.parent)
    try:
        expected = path.parent.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        problems.append("profile directory is outside the selected hardware profiles root")
        return problems

    slug = document.get("profile", {}).get("slug")
    if slug != expected:
        problems.append(f"slug {slug!r} does not match the directory {expected!r}")
    return problems


def discover_profiles(root: Path) -> tuple[list[Path], list[Path], list[str]]:
    """Find declared profiles and evidence bundles without silently skipping either."""
    profile_files = sorted(root.glob("*/*/profile.scm"))
    evidence_files = sorted(root.glob("*/*/evidence.json"))
    problems: list[str] = []

    for profile_file in profile_files:
        if profile_file.is_symlink():
            problems.append(f"{profile_file}: profile.scm must not be a symlink")
            continue
        evidence_file = profile_file.parent / "evidence.json"
        if not evidence_file.is_file():
            problems.append(f"{profile_file.parent}: profile.scm has no evidence.json")
        elif evidence_file.is_symlink():
            problems.append(f"{evidence_file}: evidence.json must not be a symlink")

    for evidence_file in evidence_files:
        if not (evidence_file.parent / "profile.scm").is_file():
            problems.append(f"{evidence_file}: evidence bundle has no matching profile.scm")

    return profile_files, evidence_files, problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-profile-evidence",
        description="Validate hardware profile evidence bundles and referenced artifacts.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="validate one evidence.json and its artifacts (does not check the directory slug)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROFILES_DIR,
        help="hardware profiles root to scan for <vendor>/<model>/profile.scm and evidence.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        if not args.file.is_file():
            print(f"check-profile-evidence: evidence file not found: {args.file}", file=sys.stderr)
            return 2
        document, read_problems = read_document(args.file)
        problems = read_problems
        if document is not None:
            problems.extend(validate(document, artifact_root=args.file.parent))
        if problems:
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            return 1
        print(f"{args.file}: ok (schema and artifact hashes; directory slug not checked)")
        return 0

    if not args.dir.is_dir():
        print(f"check-profile-evidence: profiles directory not found: {args.dir}", file=sys.stderr)
        return 2

    profile_files, evidence_files, discovery_problems = discover_profiles(args.dir)
    failures = len(discovery_problems)

    for problem in discovery_problems:
        print(f"- {problem}", file=sys.stderr)

    for target in evidence_files:
        problems = validate_directory(target, args.dir)
        if problems:
            failures += 1
            print(f"{target}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            print(f"{target}: ok")

    if failures:
        print(f"check-profile-evidence: {failures} profile/evidence problem(s)", file=sys.stderr)
        return 1

    if not profile_files and not evidence_files:
        print("check-profile-evidence: no hardware profiles registered yet")
        return 0

    print(
        f"check-profile-evidence: {len(evidence_files)} bundle(s) accepted "
        f"for {len(profile_files)} profile(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
