# SPDX-License-Identifier: LicenseRef-Volnist
"""Single source of truth for hardware profile evidence validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "profile-evidence.schema.json"

SUPPORTED_SCHEMA = "wsm-profile-evidence/2"


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


def _safe_relative_path_problem(raw_path: str, label: str) -> str | None:
    """Reject absolute, traversing, non-canonical or platform-specific paths."""
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
        return f"{label}/path is not a safe relative path: {raw_path!r}"
    return None


def _file_sha256_problem(
    raw_path: str,
    expected_sha256: str,
    artifact_root: Path | None,
    label: str,
) -> list[str]:
    """Verify one safe relative file path and its exact SHA-256."""
    unsafe_path = _safe_relative_path_problem(raw_path, label)
    if unsafe_path:
        return [unsafe_path]
    relative = PurePosixPath(raw_path)

    if artifact_root is None:
        return [f"{label} cannot be verified without an evidence directory"]
    if artifact_root.is_symlink():
        return [f"{label} evidence directory must not be a symbolic link"]

    try:
        root = artifact_root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        return [f"{label} evidence directory is unavailable: {exc}"]
    if not root.is_dir():
        return [f"{label} evidence root is not a directory"]

    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        try:
            if candidate.is_symlink():
                return [f"{label}/path must not traverse a symbolic link"]
        except (OSError, ValueError):
            return [f"{label}/path contains an invalid filesystem component"]

    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return [f"{label}/path is missing or escapes the evidence directory"]

    try:
        if not resolved.is_file():
            return [f"{label}/path is not a regular file"]
        if resolved.stat().st_size == 0:
            return [f"{label}/path must not be an empty file"]
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, ValueError):
        return [f"{label}/path cannot be read"]

    if digest.hexdigest() != expected_sha256:
        return [f"{label}/sha256 does not match the bytes at {raw_path!r}"]
    return []


def _artifact_problems(
    artifact: dict[str, Any],
    artifact_root: Path | None,
    index: int,
) -> list[str]:
    """Verify one manifest artifact is stored under artifacts/ and matches its bytes."""
    raw_path = artifact["path"]
    if not raw_path.startswith("artifacts/"):
        return [f"artifacts/{index}/path must be stored under the profile's artifacts/ directory"]
    return _file_sha256_problem(
        raw_path,
        artifact["sha256"],
        artifact_root,
        f"artifacts/{index}",
    )

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
    version = document.get("schema") if isinstance(document, dict) else None
    if version != SUPPORTED_SCHEMA:
        return [
            f"schema-version: {version!r} is not {SUPPORTED_SCHEMA!r}; "
            "this reader does not upgrade an unknown bundle version"
        ]

    # Report path-safety violations before JSON Schema shape errors so callers
    # receive the actionable filesystem reason (absolute path / traversal).
    early_path_problems: list[str] = []
    profile_source = document.get("profile_source")
    if isinstance(profile_source, dict) and isinstance(profile_source.get("path"), str):
        issue = _safe_relative_path_problem(profile_source["path"], "profile_source")
        if issue:
            early_path_problems.append(issue)
    raw_artifacts = document.get("artifacts")
    if isinstance(raw_artifacts, list):
        for index, artifact in enumerate(raw_artifacts):
            if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                issue = _safe_relative_path_problem(artifact["path"], f"artifacts/{index}")
                if issue:
                    early_path_problems.append(issue)
    if early_path_problems:
        return early_path_problems

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
    artifact_by_path: dict[str, dict[str, Any]] = {}
    for artifact in document["artifacts"]:
        path = artifact["path"]
        if path in artifact_by_path:
            found.append(
                f"duplicate artifact path {path!r}; each path must have exactly one manifest entry"
            )
            continue
        artifact_by_path[path] = artifact

    source_reports = [
        artifact
        for artifact in document["artifacts"]
        if artifact["kind"] == "wsm-hwcheck-report"
    ]
    if len(source_reports) != 1:
        found.append(
            "evidence must contain exactly one wsm-hwcheck-report artifact"
        )
    source_report_sha256 = source_reports[0]["sha256"] if len(source_reports) == 1 else None
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
                elif artifact["kind"] != "functional-test-log":
                    found.append(
                        f"function {item['name']!r} references non-functional artifact kind {artifact['kind']!r}"
                    )
                elif source_report_sha256 is not None and artifact["sha256"] == source_report_sha256:
                    found.append(
                        f"function {item['name']!r} references bytes identical to the source hardware report; add a distinct functional test artifact"
                    )
        if status == "fail" and item["name"].lower() not in limitations:
            found.append(
                f"function {item['name']!r} failed but is not listed in known_limitations"
            )

    profile_source = document["profile_source"]
    found.extend(
        _file_sha256_problem(
            profile_source["path"],
            profile_source["sha256"],
            artifact_root,
            "profile_source",
        )
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
