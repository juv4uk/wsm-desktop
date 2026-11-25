# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone, review-only CLI for preparing a GNU Guix handoff.

This command validates a confirmed plan and explicit target selection, then
writes a reviewable operating-system configuration outside the target mount.
It prints the ordered argv as JSON; it never executes Guix or mutates a target.
"""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
import os
from pathlib import Path
import sys
from typing import Any

from .backend_guix import HandoffError, TargetSelection, prepare

MAX_INPUT_BYTES = 2 * 1024 * 1024
CONFIRMATION_KEYS = {"confirmed", "plan_sha256", "target_digest"}


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON object from a local file."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label}: cannot read {path}: {exc}") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"{label}: input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: expected valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: JSON root must be an object")
    return value


def _selection_from_json(value: dict[str, Any]) -> TargetSelection:
    expected = {item.name for item in fields(TargetSelection)}
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(
            f"selection: fields must match TargetSelection exactly; "
            f"missing={missing}, extra={extra}"
        )
    if any(not isinstance(item, str) for item in value.values()):
        raise ValueError("selection: every field must be a string")
    return TargetSelection(**value)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_output_path(raw_output: str, raw_mountpoint: str) -> Path:
    """Require a new .scm file on the live filesystem, outside the target mount."""
    output = Path(raw_output)
    mountpoint = Path(raw_mountpoint)
    if not output.is_absolute():
        raise ValueError("output path must be absolute")
    if output.suffix != ".scm":
        raise ValueError("output file must have the .scm suffix")
    if not mountpoint.is_absolute() or mountpoint == Path("/"):
        raise ValueError("target mountpoint must be an absolute non-root path")
    try:
        target_root = mountpoint.resolve(strict=True)
        parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"output parent and target mountpoint must already exist: {exc}") from exc
    if not target_root.is_dir() or not parent.is_dir():
        raise ValueError("output parent and target mountpoint must be directories")
    if _is_within(parent, target_root):
        raise ValueError("refusing to write the configuration inside the target mountpoint")
    for protected in (Path("/dev"), Path("/proc"), Path("/sys")):
        try:
            protected_root = protected.resolve(strict=True)
        except OSError:
            continue
        if _is_within(parent, protected_root):
            raise ValueError(f"refusing to write the configuration under {protected}")
    resolved_output = parent / output.name
    if resolved_output.exists() or resolved_output.is_symlink():
        raise ValueError(f"output already exists; refusing to overwrite: {resolved_output}")
    return resolved_output


def _write_new_configuration(path: Path, configuration: str) -> None:
    """Create a new private file; do not overwrite an existing path or symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    created = True
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(configuration)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a confirmed WSM plan and emit a reviewable GNU Guix "
            "configuration. This command never runs Guix or writes to the target."
        )
    )
    parser.add_argument("--plan", required=True, type=Path, help="validated install-plan JSON")
    parser.add_argument("--selection", required=True, type=Path, help="explicit target-selection JSON")
    parser.add_argument("--confirmation", required=True, type=Path, help="confirmation receipt JSON")
    parser.add_argument("--output", required=True, help="new absolute .scm file outside the target mount")
    parser.add_argument("--target-mountpoint", default="/mnt", help="mounted target root (default: /mnt)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = _read_json_object(args.plan, label="plan")
        selection_payload = _read_json_object(args.selection, label="selection")
        confirmation = _read_json_object(args.confirmation, label="confirmation")
        if set(confirmation) != CONFIRMATION_KEYS:
            raise ValueError(
                "confirmation: fields must be exactly confirmed, plan_sha256, target_digest"
            )
        if confirmation.get("confirmed") is not True:
            raise ValueError("confirmation: explicit confirmed=true receipt is required")

        selection = _selection_from_json(selection_payload)
        output_path = _validate_output_path(args.output, args.target_mountpoint)
        handoff = prepare(
            plan,
            selection,
            confirmed_plan_sha256=str(confirmation.get("plan_sha256", "")),
            confirmed_target_digest=str(confirmation.get("target_digest", "")),
            configuration_path=str(output_path),
            target_mountpoint=args.target_mountpoint,
        )
        _write_new_configuration(output_path, handoff.configuration)

        manifest = {
            "backend_id": handoff.backend_id,
            "adapter_version": handoff.adapter_version,
            "configuration_path": str(output_path),
            "configuration_sha256": handoff.configuration_sha256,
            "target_digest": handoff.target_digest,
            "plan_sha256": handoff.plan_sha256,
            "argv": list(handoff.argv),
            "executed": False,
        }
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (HandoffError, OSError, TypeError, ValueError) as exc:
        print(f"wsm-guix-handoff: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
