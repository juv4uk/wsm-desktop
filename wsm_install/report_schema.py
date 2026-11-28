# SPDX-License-Identifier: LicenseRef-Volnist
"""Published hardware-report schemas, selected by the version a report declares.

Report format 1.1.0 adds optional device facts (``cpu``, ``gpu``, ``network``,
``storage``), ``environment.boot_mode_evidence`` and
``environment.platform.bios_release``. Nothing became required, so a 1.0.0
report describes a subset of the current format.

It is still validated against the *frozen 1.0.0 schema*, not against the
current file: the current file pins ``schema_version`` to 1.1.0, so reading a
1.0.0 report with it would reject a document that is perfectly valid under the
contract it declares. Selecting by declared version keeps old reports readable
and keeps "we validated it" an honest claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

CURRENT_VERSION = "1.1.0"
CURRENT_SCHEMA = SCHEMA_DIR / "hardware-report.schema.json"
FROZEN_SCHEMAS = {
    "1.0.0": SCHEMA_DIR / "hardware-report-1.0.0.schema.json",
}
SUPPORTED_VERSIONS = ("1.0.0", CURRENT_VERSION)


class UnsupportedSchemaVersion(ValueError):
    """The report declares a schema version this tree cannot validate."""


def schema_path_for(version: str | None) -> Path:
    """Return the published schema file for a declared report version."""
    if version == CURRENT_VERSION:
        return CURRENT_SCHEMA
    frozen = FROZEN_SCHEMAS.get(version or "")
    if frozen is not None and frozen.is_file():
        return frozen
    raise UnsupportedSchemaVersion(
        f"unsupported hardware report schema {version!r}; "
        f"supported: {', '.join(SUPPORTED_VERSIONS)}"
    )


def load_schema(version: str | None) -> dict[str, Any]:
    """Load the published schema for a declared report version."""
    document = json.loads(schema_path_for(version).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise UnsupportedSchemaVersion(f"schema for {version!r} is not a JSON object")
    return document
