# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate hardware profile evidence bundles and their referenced artifacts.

A profile is a claim about a specific machine. It needs a valid evidence bundle,
and every artifact digest must resolve to bytes stored inside that profile.
The directory scanner also rejects profile.scm files without evidence.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "profile-evidence.schema.json"
PROFILES_DIR = ROOT / "profiles" / "hardware"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    artifact_root: Path | None = None,
) -> list[str]:
    """Return problems. artifact_root enables on-disk path and digest checks."""
    schema = schema or load_schema()
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        return [f"schema: {location}: {exc.message}"]

    problems: list[str] = []
    functions = document["verified_functions"]
    if not any(item["status"] == "pass" for item in functions):
        problems.append(
            "no function passed: a bundle with only not-assessed entries is a "
            "hypothesis, not evidence"
        )

    failed = [item["name"] for item in functions if item["status"] == "fail"]
    limitations = " ".join(document["known_limitations"]).lower()
    for name in failed:
        if name.lower() not in limitations:
            problems.append(
                f"function {name!r} failed but is not listed in known_limitations"
            )

    if artifact_root is not None:
        problems.extend(validate_artifact_files(document["artifacts"], artifact_root))

    return problems


def validate_artifact_files(artifacts: list[dict[str, Any]], root: Path) -> list[str]:
    """Verify safe relative artifact paths and their SHA-256 digests."""
    problems: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return ["profile directory must be a real directory, not a symlink or missing path"]
    root_path = root.resolve()

    for artifact in artifacts:
        relative = artifact["path"]
        raw_parts = relative.split("/")
        posix_path = PurePosixPath(relative)
        if (
            "\\" in relative
            or relative.startswith("/")
            or posix_path.is_absolute()
            or not posix_path.parts
            or any(part in {"", ".", ".."} for part in raw_parts)
        ):
            problems.append(
                f"artifact path {relative!r} must be a safe relative path under the profile directory"
            )
            continue

        candidate = root
        has_symlink = False
        for part in posix_path.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                has_symlink = True
                break
        if has_symlink:
            problems.append(f"artifact path {relative!r} must not traverse a symlink")
            continue

        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_path)
        except (OSError, ValueError):
            problems.append(f"artifact path {relative!r} is missing or escapes the profile directory")
            continue

        if not resolved.is_file():
            problems.append(f"artifact path {relative!r} is not a regular file")
            continue

        digest = hashlib.sha256()
        try:
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            problems.append(f"artifact path {relative!r} cannot be read: {exc}")
            continue

        actual = digest.hexdigest()
        if actual != artifact["sha256"]:
            problems.append(
                f"artifact path {relative!r} sha256 mismatch: "
                f"expected {artifact['sha256']}, got {actual}"
            )

    return problems


def read_document(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read evidence JSON: {exc}"]
    if not isinstance(document, dict):
        return None, ["evidence JSON root must be an object"]
    return document, []


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
