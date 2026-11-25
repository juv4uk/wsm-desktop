# SPDX-License-Identifier: LicenseRef-Volnist
"""Hardware profile evidence: the gate between "we tested this" and "try it".

The rule from docs/HARDWARE-PROFILE-EVIDENCE.md is that a profile without an
evidence bundle does not take part in an installation. This module is where that
rule is enforced, so it holds for the installer and for the standalone checker
alike - one implementation, one behaviour.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "profile-evidence.schema.json"


class EvidenceUnavailable(Exception):
    """The bundle could not be read at all, as opposed to being invalid."""


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceUnavailable(f"cannot read evidence bundle {path}: {exc}") from exc


def problems(document: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    """Return every reason this bundle is not evidence. Empty means acceptable."""
    schema = schema or load_schema()
    found: list[str] = []

    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a test dependency
        raise EvidenceUnavailable(
            "jsonschema is required to validate evidence bundles"
        ) from None

    try:
        jsonschema.validate(document, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        return [f"schema: {location}: {exc.message}"]

    functions = document["verified_functions"]
    if not any(item["status"] == "pass" for item in functions):
        found.append(
            "no function passed: a bundle with only not-assessed entries is a "
            "hypothesis, not evidence"
        )

    limitations = " ".join(document["known_limitations"]).lower()
    for item in functions:
        if item["status"] == "fail" and item["name"].lower() not in limitations:
            found.append(
                f"function {item['name']!r} failed but is not listed in known_limitations"
            )

    if EMAIL.search(document["verified_by"]):
        found.append("verified_by must not contain an e-mail address")

    return found


def slug_matches_directory(document: dict[str, Any], directory: Path, root: Path) -> list[str]:
    expected = directory.relative_to(root).as_posix()
    slug = document["profile"]["slug"]
    if slug != expected:
        return [f"slug {slug!r} does not match the directory {expected!r}"]
    return []
