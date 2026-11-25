# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate hardware profile evidence bundles and their referenced artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "profile-evidence.schema.json"
PROFILES_DIR = ROOT / "profiles" / "hardware"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.profile import problems as profile_problems  # noqa: E402


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_document(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"cannot read JSON: {exc}"]
    if not isinstance(value, dict):
        return None, ["evidence document must be a JSON object"]
    return value, []


def _validate_artifact(
    artifact: dict[str, Any],
    artifact_root: Path | None,
    index: int,
) -> list[str]:
    problems: list[str] = []
    raw_path = artifact["path"]

    # Use portable POSIX relative paths in the manifest; never accept a path
    # that could escape the evidence directory or become absolute on Windows.
    parts = raw_path.split("/")
    relative = PurePosixPath(raw_path)
    if (
        not raw_path
        or "\\" in raw_path
        or ":" in raw_path
        or relative.is_absolute()
        or any(part in ("", ".", "..") for part in parts)
        or relative.as_posix() != raw_path
    ):
        return [f"artifacts/{index}/path is not a safe relative path: {raw_path!r}"]

    if artifact_root is None:
        return [f"artifacts/{index} cannot be verified without an evidence directory"]

    try:
        root = artifact_root.resolve(strict=True)
    except OSError as exc:
        return [f"artifacts/{index} evidence directory is unavailable: {exc}"]
    if not root.is_dir():
        return [f"artifacts/{index} evidence root is not a directory"]

    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return [f"artifacts/{index}/path must not traverse a symbolic link"]

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        return [f"artifacts/{index}/path does not resolve to a file: {exc}"]

    if not resolved.is_relative_to(root):
        return [f"artifacts/{index}/path escapes the evidence directory"]
    if not resolved.is_file():
        return [f"artifacts/{index}/path is not a regular file"]

    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return [f"artifacts/{index}/path cannot be read: {exc}"]

    if digest.hexdigest() != artifact["sha256"]:
        problems.append(
            f"artifacts/{index}/sha256 does not match the bytes at {raw_path!r}"
        )
    return problems


def validate(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
) -> list[str]:
    """Apply the installer's shared schema/semantic gate, then verify local artifact bytes."""
    problems = profile_problems(document, schema)
    for index, artifact in enumerate(document["artifacts"]):
        problems.extend(_validate_artifact(artifact, artifact_root, index))
    return problems


def validate_directory(path: Path, profiles_dir: Path = PROFILES_DIR) -> list[str]:
    """Validate a model directory's evidence.json, slug and referenced files."""
    if path.is_symlink():
        return ["evidence.json must not be a symbolic link"]
    document, read_problems = _load_document(path)
    if read_problems or document is None:
        return read_problems

    problems = validate(document, artifact_root=path.parent)
    if problems:
        return problems

    try:
        root = profiles_dir.resolve(strict=True)
        model_dir = path.parent.resolve(strict=True)
        relative = model_dir.relative_to(root)
    except (OSError, ValueError) as exc:
        return [f"evidence directory is outside the profiles root: {exc}"]

    if len(relative.parts) != 2:
        problems.append("profile directory must be exactly <vendor>/<model>")
        return problems

    expected_slug = relative.as_posix()
    actual_slug = document["profile"]["slug"]
    if actual_slug != expected_slug:
        problems.append(
            f"slug {actual_slug!r} does not match the directory {expected_slug!r}"
        )
    return problems


def discover_profile_directories(profiles_dir: Path) -> tuple[list[Path], list[str]]:
    """Discover every tracked-depth vendor/model directory; reject symlink dirs."""
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
        help="scan <vendor>/<model> directories for mandatory evidence.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        target = args.file
        document, problems = _load_document(target)
        if document is not None:
            problems = validate(document, artifact_root=target.parent)
        if problems:
            print(f"{target}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"{target}: schema and artifact checks passed (directory slug not checked)")
        return 0

    profiles_dir = args.dir
    if not profiles_dir.is_dir():
        print(f"check-profile-evidence: no profiles directory at {profiles_dir}", file=sys.stderr)
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
        target = model_dir / "evidence.json"
        if not target.is_file():
            failures += 1
            print(f"{model_dir}:", file=sys.stderr)
            print("  - missing mandatory evidence.json; this directory is not an accepted profile", file=sys.stderr)
            continue

        problems = validate_directory(target, profiles_dir)
        if problems:
            failures += 1
            print(f"{target}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            accepted += 1
            print(f"{target}: ok")

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
