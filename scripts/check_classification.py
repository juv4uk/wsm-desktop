# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate a stored `wsm-hardware-classification/2` summary.

The classifier emits a versioned artifact, so it gets what every other versioned
artifact in this repository has: a schema, a reader that refuses an unknown
version, and rules the schema cannot express.

Rules a schema cannot express:

* `counts` must describe the subsystems that are actually listed. A summary
  whose counts disagree with its own contents is worse than no summary: it looks
  like a measurement.
* a subsystem may appear once. Two rows for `storage` mean the reader has to
  pick one, and picking is guessing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "hardware-classification.schema.json"
SUPPORTED_VERSION = "wsm-hardware-classification/2"
LEVELS = ("certified", "known", "unknown")


class ClassificationError(Exception):
    """A refusal with a stable code, like the rest of the project."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def problems(document: object, schema: dict | None = None) -> list[str]:
    """Return every reason this summary is not acceptable. Empty list means OK."""
    schema = schema or load_schema()

    if not isinstance(document, dict):
        return ["classification: document must be a JSON object"]

    version = document.get("schema")
    if version != SUPPORTED_VERSION:
        return [
            f"classification.schema-version: {version!r} is not {SUPPORTED_VERSION!r}; "
            f"this reader does not upgrade an unknown summary version"
        ]

    found: list[str] = []
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        found.append(f"classification.schema: {location}: {error.message}")

    subsystems = document.get("subsystems")
    counts = document.get("counts")
    if isinstance(subsystems, list) and isinstance(counts, dict):
        names = [
            item.get("subsystem")
            for item in subsystems
            if isinstance(item, dict)
        ]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            found.append(f"classification.subsystem: {name!r} appears more than once")

        actual = {level: 0 for level in LEVELS}
        for item in subsystems:
            if isinstance(item, dict) and item.get("level") in actual:
                actual[item["level"]] += 1
        for level in LEVELS:
            declared = counts.get(level)
            if declared != actual[level]:
                found.append(
                    f"classification.counts: {level} says {declared!r} but "
                    f"{actual[level]} subsystems have that level"
                )

    return found


def validate_file(path: Path) -> list[str]:
    return problems(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a WSM classification summary.")
    parser.add_argument("path", help="classification JSON file")
    arguments = parser.parse_args(argv)

    found = validate_file(Path(arguments.path))
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    print(f"Classification summary is valid ({SUPPORTED_VERSION}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
