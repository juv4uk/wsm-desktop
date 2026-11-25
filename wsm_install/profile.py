# SPDX-License-Identifier: LicenseRef-Volnist
"""Hardware profile evidence: the gate between "we tested this" and "try it".

The rule from docs/HARDWARE-PROFILE-EVIDENCE.md is that a profile without an
evidence bundle does not take part in an installation. This module is where that
rule is enforced, so it holds for the installer and for the standalone checker
alike - one implementation, one behaviour.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
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


def problems(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
) -> list[str]:
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

    if artifact_root is not None:
        found.extend(validate_artifact_files(document, artifact_root))

    return found


def validate_artifact_files(
    document: dict[str, Any],
    root: Path,
) -> list[str]:
    """Verify profile files and SHA-256 digests against the supplied evidence bundle."""
    problems: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return ["profile directory must be a real directory, not a symlink or missing path"]
    root_path = root.resolve()

    for required_name in ("profile.scm", "evidence.json"):
        required_path = root / required_name
        if required_path.is_symlink() or not required_path.is_file():
            problems.append(f"profile directory is missing mandatory regular file {required_name!r}")

    evidence_path = root / "evidence.json"
    if evidence_path.is_file() and not evidence_path.is_symlink():
        try:
            on_disk = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            problems.append(f"evidence.json cannot be read as UTF-8 JSON: {exc}")
        else:
            if on_disk != document:
                problems.append("supplied evidence bundle does not match the profile's evidence.json bytes")

    artifacts = document["artifacts"]
    for artifact in artifacts:
        relative = artifact["path"]
        raw_parts = relative.split("/")
        posix_path = PurePosixPath(relative)
        if (
            "\\" in relative
            or relative.startswith("/")
            or posix_path.is_absolute()
            or bool(PureWindowsPath(relative).drive)
            or ":" in relative
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


def slug_matches_directory(document: dict[str, Any], directory: Path, root: Path) -> list[str]:
    expected = directory.relative_to(root).as_posix()
    slug = document["profile"]["slug"]
    if slug != expected:
        return [f"slug {slug!r} does not match the directory {expected!r}"]
    return []
