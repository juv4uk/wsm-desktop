# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate release metadata against a versioned schema.

`RELEASE-INFO.json` is what a person reads first and what the release scripts
consume. Until now its shape was held together by ad-hoc tests: nothing refused
an unknown schema version, a missing `excluded` list or an artifact name that
quietly points outside the release directory.

The schema covers shape. This script covers the rules a schema cannot express:

* the version must appear in the artifact names, so metadata cannot describe a
  different release than the files it lists;
* artifact names are bare file names - no directories, no `..`, no absolute
  paths, because these strings end up in build and publish commands;
* `excluded` must say something: a release that excludes nothing is either
  complete or not being honest about what it left out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "release-info.schema.json"
SUPPORTED_VERSION = "wsm-release-info/1"


class ReleaseInfoError(Exception):
    """A refusal with a stable code, like the rest of the installer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def problems(document: object, schema: dict | None = None) -> list[str]:
    """Return every reason this document is not acceptable. Empty list means OK."""
    schema = schema or load_schema()

    if not isinstance(document, dict):
        return ["release-info: document must be a JSON object"]

    version = document.get("schema")
    if version != SUPPORTED_VERSION:
        return [
            f"release-info.schema-version: {version!r} is not {SUPPORTED_VERSION!r}; "
            f"a reader must refuse an unknown version instead of guessing"
        ]

    found: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        found.append(f"release-info.schema: {location}: {error.message}")

    artifacts = document.get("artifacts")
    release_version = document.get("version")
    if isinstance(artifacts, list) and isinstance(release_version, str):
        if not any(release_version in name for name in artifacts if isinstance(name, str)):
            found.append(
                "release-info.version: no artifact name carries the version "
                f"{release_version!r}; metadata would describe another release"
            )
        for name in artifacts:
            if not isinstance(name, str):
                continue
            if "/" in name or "\\" in name or name in {".", ".."}:
                found.append(
                    f"release-info.artifact-path: {name!r} is not a bare file name"
                )

    excluded = document.get("excluded")
    if isinstance(excluded, list) and not excluded:
        found.append("release-info.excluded: an empty exclusion list claims completeness")

    return found


def validate_file(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return problems(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate WSM release metadata.")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "RELEASE-INFO.json"),
        help="release metadata file (default: RELEASE-INFO.json)",
    )
    arguments = parser.parse_args(argv)

    found = validate_file(Path(arguments.path))
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    print(f"Release metadata is valid ({SUPPORTED_VERSION}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
