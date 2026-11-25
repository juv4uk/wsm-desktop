# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a confirmed Guix handoff without executing deployment commands."""

from __future__ import annotations

import argparse
from dataclasses import fields
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from .backend_guix import (
    GUIX_CONFIGURATION_PATH,
    GUIX_TARGET_MOUNTPOINT,
    HandoffError,
    TargetSelection,
    prepare,
    validate_plan,
    validate_selection,
)

MAX_INPUT_BYTES = 2 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DeployCliError(Exception):
    """A safe refusal before creating the generated configuration."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _read_json_object(path_value: str, label: str) -> tuple[dict[str, Any], Path]:
    """Read one bounded regular JSON file, refusing symlinks and duplicate keys."""
    path = Path(path_value)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DeployCliError(f"cannot open {label}: {exc}") from exc

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DeployCliError(f"{label} must be a regular file (symlinks are refused)")
        if metadata.st_size > MAX_INPUT_BYTES:
            raise DeployCliError(f"{label} exceeds the {MAX_INPUT_BYTES}-byte limit")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise DeployCliError(f"{label} exceeds the {MAX_INPUT_BYTES}-byte limit")
    finally:
        os.close(descriptor)

    try:
        value = json.loads(
            b"".join(chunks).decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DeployCliError(f"{label} is not valid unambiguous UTF-8 JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise DeployCliError(f"{label} must contain a JSON object")

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise DeployCliError(f"cannot resolve {label} path: {exc}") from exc
    return value, resolved


def _validate_plan_shape(plan: dict[str, Any]) -> None:
    """Reject malformed nested fields before the stricter adapter validator reads them."""
    for key in ("backend", "plan_readiness", "execution", "source_report"):
        if not isinstance(plan.get(key), dict):
            raise DeployCliError(f"plan field {key!r} must be a JSON object")
    if not isinstance(plan.get("blockers"), list):
        raise DeployCliError("plan field 'blockers' must be a JSON array")
    if not isinstance(plan.get("plan_sha256"), str):
        raise DeployCliError("plan field 'plan_sha256' must be a string")


def _load_selection(value: dict[str, Any]) -> TargetSelection:
    expected = {item.name for item in fields(TargetSelection)}
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DeployCliError(
            f"selection keys do not match the contract (missing={missing}, extra={extra})"
        )
    if any(not isinstance(item, str) for item in value.values()):
        raise DeployCliError("every target selection value must be a JSON string")

    selection = TargetSelection(**value)
    validate_selection(selection)
    return selection


def _ensure_output_outside_target(destination: Path) -> None:
    """Never write a review copy into the installer-owned target mount root."""
    target = Path(GUIX_TARGET_MOUNTPOINT).resolve(strict=False)
    if destination == target or target in destination.parents:
        raise DeployCliError(
            "configuration output must be outside the target mountpoint "
            "to avoid writing to the target filesystem"
        )


def _resolve_output(
    output_value: str,
    protected_inputs: tuple[Path, ...],
) -> Path:
    requested = Path(output_value)
    if not requested.is_absolute():
        raise DeployCliError("configuration output path must be absolute")
    if requested.suffix != ".scm" or not requested.name:
        raise DeployCliError("configuration output must use the .scm suffix")

    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise DeployCliError(f"configuration output parent is unavailable: {exc}") from exc
    if not parent.is_dir():
        raise DeployCliError("configuration output parent is not a directory")

    destination = parent / requested.name
    for protected in protected_inputs:
        if destination == protected:
            raise DeployCliError("configuration output must not overwrite an input file")

    for special_root in (Path("/dev"), Path("/proc"), Path("/sys")):
        try:
            special = special_root.resolve(strict=True)
        except OSError:
            continue
        if destination == special or special in destination.parents:
            raise DeployCliError(f"configuration output is not allowed under {special}")

    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise DeployCliError(f"cannot inspect configuration output: {exc}") from exc
    else:
        raise DeployCliError("configuration output already exists; refusing to overwrite it")

    return destination


def _write_new_file(destination: Path, content: str) -> None:
    """Create a new private file atomically with O_EXCL and no symlink following."""
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(destination, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        payload = content.encode("utf-8")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write while creating configuration")
            offset += written
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-guix-deploy",
        description=(
            "Validate a confirmed WSM plan and prepare a reviewable Guix configuration. "
            "This command never runs guix system init."
        ),
    )
    parser.add_argument("--version", action="version", version="wsm-guix-deploy 0.1.0")
    parser.add_argument("--plan", required=True, metavar="PATH", help="confirmed install plan JSON")
    parser.add_argument("--selection", required=True, metavar="PATH", help="explicit target selection JSON")
    parser.add_argument(
        "--show-confirmation",
        action="store_true",
        help="validate inputs and print the exact digests required by the prepare step",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help=(
            "new absolute .scm review copy; existing files are never overwritten. "
            f"The displayed deployment argv always uses the installer-owned path {GUIX_CONFIGURATION_PATH}."
        ),
    )
    parser.add_argument("--confirm-plan-sha256", metavar="HEX", help="plan digest explicitly confirmed by the caller")
    parser.add_argument("--confirm-target-digest", metavar="HEX", help="target digest explicitly confirmed by the caller")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        plan, plan_path = _read_json_object(args.plan, "plan")
        selection_data, selection_path = _read_json_object(args.selection, "selection")
        selection = _load_selection(selection_data)
        _validate_plan_shape(plan)
        validate_plan(plan)

        target_digest = selection.digest()
        plan_digest = plan["plan_sha256"]

        if args.show_confirmation:
            if args.output or args.confirm_plan_sha256 or args.confirm_target_digest:
                raise DeployCliError(
                    "--show-confirmation cannot be combined with output or confirmation arguments"
                )
            print(
                json.dumps(
                    {
                        "status": "confirmation-required",
                        "backend_id": "guix-system",
                        "plan_sha256": plan_digest,
                        "target_digest": target_digest,
                        "target_disk": selection.disk,
                        "boot_mode": selection.boot_mode,
                        "configuration_created": False,
                        "deployment_executed": False,
                        "target_disk_mutated": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
            )
            return 0

        if not args.output:
            raise DeployCliError("--output is required unless --show-confirmation is used")
        if not args.confirm_plan_sha256 or not args.confirm_target_digest:
            raise DeployCliError(
                "both --confirm-plan-sha256 and --confirm-target-digest are required"
            )
        if not SHA256_PATTERN.fullmatch(args.confirm_plan_sha256):
            raise DeployCliError("--confirm-plan-sha256 must be 64 lowercase hexadecimal characters")
        if not SHA256_PATTERN.fullmatch(args.confirm_target_digest):
            raise DeployCliError("--confirm-target-digest must be 64 lowercase hexadecimal characters")
        if args.confirm_plan_sha256 != plan_digest:
            raise HandoffError("confirmation.plan_sha256", "the confirmed plan digest does not match the input")
        if args.confirm_target_digest != target_digest:
            raise HandoffError("confirmation.target_digest", "the confirmed target digest does not match the input")

        destination = _resolve_output(
            args.output,
            (plan_path, selection_path),
        )
        _ensure_output_outside_target(destination)
        handoff = prepare(
            plan,
            selection,
            confirmed_plan_sha256=args.confirm_plan_sha256,
            confirmed_target_digest=args.confirm_target_digest,
            external_bootloader_job=False,
            configuration_path=GUIX_CONFIGURATION_PATH,
            target_mountpoint=GUIX_TARGET_MOUNTPOINT,
        )

        _write_new_file(destination, handoff.configuration)
        print(
            json.dumps(
                {
                    "status": "prepared-not-executed",
                    "backend_id": handoff.backend_id,
                    "adapter_version": handoff.adapter_version,
                    "configuration_path": str(destination),
                    "configuration_sha256": handoff.configuration_sha256,
                    "plan_sha256": handoff.plan_sha256,
                    "target_digest": handoff.target_digest,
                    "target_disk": selection.disk,
                    "argv": list(handoff.argv),
                    "deployment_executed": False,
                    "target_disk_mutated": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    except HandoffError as exc:
        print(f"wsm-guix-deploy: refused [{exc.code}]: {exc.message}", file=sys.stderr)
        return 3
    except (DeployCliError, OSError, TypeError, ValueError, AttributeError) as exc:
        print(f"wsm-guix-deploy: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
