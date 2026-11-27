# SPDX-License-Identifier: LicenseRef-Volnist
"""Shared hardware-report schema validation for CLI and GUI frontends."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"


class SchemaUnavailableError(RuntimeError):
    """The canonical hardware-report schema could not be loaded or checked."""


class ReportSchemaError(ValueError):
    """A report is malformed or fails the canonical hardware-report schema."""

    def __init__(self, errors: tuple[tuple[str, str], ...]):
        self.errors = errors
        detail = "; ".join(f"{location}: {message}" for location, message in errors[:5])
        super().__init__(detail or "hardware report is invalid")


def validate_report(
    report: dict[str, Any],
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> tuple[tuple[str, str], ...]:
    """Return canonical schema errors without mutating the report or host."""
    if not isinstance(report, dict):
        return (("$", "top-level value must be an object"),)

    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SchemaUnavailableError(f"cannot load hardware report schema: {exc}") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(report),
        key=lambda item: list(item.absolute_path),
    )
    return tuple(
        (
            ".".join(str(part) for part in item.absolute_path) or "$",
            item.message,
        )
        for item in errors
    )


def require_valid_report(
    report: dict[str, Any],
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> None:
    """Raise ReportSchemaError if REPORT does not satisfy the canonical schema."""
    errors = validate_report(report, schema_path)
    if errors:
        raise ReportSchemaError(errors)
