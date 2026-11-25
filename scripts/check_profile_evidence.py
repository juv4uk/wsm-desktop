# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate hardware profile evidence bundles.

A hardware profile is a claim about a machine. The rule of this repository is
that a claim needs evidence: the bundle below is what separates "we tested this
H170" from "we think this H170 should work".

The JSON Schema covers shape. This script covers the rules a schema cannot
express:

* at least one function actually passed - a bundle where everything is
  not-assessed proves nothing;
* if any function failed, the failure must appear in known-limitations,
  otherwise the profile reads as healthy while it is not;
* e-mail addresses are rejected; contributors use a generic attribution role;
* each declared artifact must exist under artifacts/ and match its SHA-256;
* the directory the bundle sits in must match the slug inside it, so a profile
  cannot be moved and keep pointing at another machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "profile-evidence.schema.json"
PROFILES_DIR = ROOT / "profiles" / "hardware"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class EvidenceError(Exception):
    pass


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(
    document: dict,
    schema: dict | None = None,
    artifacts_base: Path | None = None,
) -> list[str]:
    """Return a list of problems. An empty list means the bundle is acceptable."""
    schema = schema or load_schema()
    problems: list[str] = []

    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        problems.append(f"schema: {location}: {exc.message}")
        return problems

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

    if EMAIL.search(document["verified_by"]):
        problems.append("verified_by must not contain an e-mail address")

    if artifacts_base is not None:
        bundle_root = artifacts_base.resolve()
        for index, artifact in enumerate(document["artifacts"]):
            relative = Path(artifact["path"])
            if (
                relative.is_absolute()
                or len(relative.parts) != 2
                or relative.parts[0] != "artifacts"
                or relative.parts[1] in ("", ".", "..")
            ):
                problems.append(f"artifact {index} has an unsafe path: {artifact['path']!r}")
                continue

            artifact_dir = bundle_root / "artifacts"
            artifact_path = bundle_root / relative
            if artifact_dir.is_symlink() or artifact_path.is_symlink():
                problems.append(f"artifact {artifact['path']!r} must not be a symlink")
                continue

            try:
                resolved = artifact_path.resolve(strict=True)
                resolved.relative_to(bundle_root)
            except (OSError, RuntimeError, ValueError):
                problems.append(f"artifact file is missing or outside the bundle: {artifact['path']!r}")
                continue

            if not resolved.is_file():
                problems.append(f"artifact path is not a regular file: {artifact['path']!r}")
                continue

            digest = hashlib.sha256()
            try:
                with resolved.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as exc:
                problems.append(f"cannot read artifact {artifact['path']!r}: {exc}")
                continue

            if digest.hexdigest() != artifact["sha256"]:
                problems.append(f"SHA-256 mismatch for artifact {artifact['path']!r}")

    return problems


def validate_directory(path: Path, profiles_dir: Path = PROFILES_DIR) -> list[str]:
    """Validate one bundle, its artifact files and its location-relative slug."""
    document = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(document, artifacts_base=path.parent)
    try:
        expected = path.parent.resolve().relative_to(profiles_dir.resolve()).as_posix()
    except ValueError:
        problems.append(
            f"bundle directory {str(path.parent)!r} is outside {str(profiles_dir)!r}"
        )
        return problems

    slug = document["profile"]["slug"]
    if slug != expected:
        problems.append(f"slug {slug!r} does not match the directory {expected!r}")
    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-profile-evidence",
        description="Validate hardware profile evidence bundles.",
    )
    parser.add_argument("--file", type=Path, help="validate one evidence.json")
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROFILES_DIR,
        help="directory to scan for <vendor>/<model>/evidence.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        targets = [args.file]
        use_directory_rules = False
    else:
        if not args.dir.is_dir():
            print(f"check-profile-evidence: no profiles directory at {args.dir}")
            return 0
        targets = sorted(args.dir.glob("*/*/evidence.json"))
        use_directory_rules = True
        if not targets:
            print("check-profile-evidence: no evidence bundles yet")
            return 0

    failures = 0
    for target in targets:
        problems = (
            validate_directory(target, args.dir)
            if use_directory_rules
            else validate(
                json.loads(target.read_text(encoding="utf-8")),
                artifacts_base=target.parent,
            )
        )
        if problems:
            failures += 1
            print(f"{target}:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
        else:
            print(f"{target}: ok")

    if failures:
        print(
            f"check-profile-evidence: {failures} bundle(s) rejected",
            file=sys.stderr,
        )
        return 1
    print(f"check-profile-evidence: {len(targets)} bundle(s) accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
