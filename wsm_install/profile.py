# SPDX-License-Identifier: LicenseRef-Volnist
"""Single source of truth for hardware profile evidence validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "profile-evidence.schema.json"


class EvidenceUnavailable(Exception):
    """The bundle or a required validator dependency could not be read."""


def load_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceUnavailable(f"cannot load profile evidence schema: {exc}") from exc


def load(path: Path) -> dict[str, Any]:
    """Load a non-symlink regular JSON file."""
    path = Path(path)
    try:
        if path.is_symlink():
            raise EvidenceUnavailable(f"evidence bundle must not be a symbolic link: {path}")
        if not path.is_file():
            raise EvidenceUnavailable(f"evidence bundle is not a regular file: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceUnavailable(f"cannot read evidence bundle {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceUnavailable(f"evidence bundle root must be a JSON object: {path}")
    return value


def _artifact_problems(
    artifact: dict[str, Any],
    artifact_root: Path | None,
    index: int,
) -> list[str]:
    """Verify one artifact's portable path, containment, file type and SHA-256."""
    raw_path = artifact["path"]
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
    if artifact_root.is_symlink():
        return [f"artifacts/{index} evidence directory must not be a symbolic link"]

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
        resolved.relative_to(root)
    except (OSError, ValueError):
        return [f"artifacts/{index}/path is missing or escapes the evidence directory"]

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
        return [f"artifacts/{index}/sha256 does not match the bytes at {raw_path!r}"]
    return []


def problems(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
) -> list[str]:
    """Return all semantic, schema, and on-disk artifact problems.

    A bundle with artifacts is not valid unless the caller supplies the directory
    containing evidence.json; this makes it impossible for the installer to
    accept a digest that has not been checked against actual bytes.
    """
    schema = schema or load_schema()

    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a runtime dependency
        raise EvidenceUnavailable("jsonschema is required to validate evidence bundles") from None

    try:
        jsonschema.validate(
            document,
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        return [f"schema: {location}: {exc.message}"]

    found: list[str] = []
    functions = document["verified_functions"]
    if not any(item["status"] == "pass" for item in functions):
        found.append(
            "no function passed: a bundle with only not-assessed entries is a "
            "hypothesis, not evidence"
        )

    limitations = " ".join(document["known_limitations"]).lower()
    artifact_by_path = {artifact["path"]: artifact for artifact in document["artifacts"]}
    for item in functions:
        status = item["status"]
        if status in {"pass", "fail"}:
            references = item.get("evidence", [])
            if not references:
                found.append(
                    f"function {item['name']!r} has status {status!r} but cites no functional evidence artifact"
                )
            for reference in references:
                artifact = artifact_by_path.get(reference)
                if artifact is None:
                    found.append(
                        f"function {item['name']!r} references missing artifact {reference!r}"
                    )
                elif artifact["kind"] == "wsm-hwcheck-report":
                    found.append(
                        f"function {item['name']!r} cites the source hardware report as functional proof; add a test artifact"
                    )
        if status == "fail" and item["name"].lower() not in limitations:
            found.append(
                f"function {item['name']!r} failed but is not listed in known_limitations"
            )

    for index, artifact in enumerate(document["artifacts"]):
        found.extend(_artifact_problems(artifact, artifact_root, index))

    return found


def slug_matches_directory(
    document: dict[str, Any],
    directory: Path,
    root: Path,
) -> list[str]:
    try:
        expected = directory.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        return [f"evidence directory is outside the profiles root: {exc}"]
    slug = document["profile"]["slug"]
    if slug != expected:
        return [f"slug {slug!r} does not match the directory {expected!r}"]
    return []
