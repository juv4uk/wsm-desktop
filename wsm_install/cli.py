# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only report validation, summary, and deterministic draft-plan output."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .plan import build_plan, canonical_json, summarize_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-install",
        description="Validate a local WSM hardware report and draft a backend plan (read-only).",
    )
    parser.add_argument("--version", action="version", version="wsm-install 0.1.0")
    parser.add_argument("--preflight", action="store_true", help="run report preflight")
    parser.add_argument("--report", required=True, metavar="PATH", help="hardware report JSON")
    parser.add_argument(
        "--backend", required=True, choices=("guix", "nix"),
        help="backend alias: guix -> guix-system; nix -> nixos",
    )
    parser.add_argument("--dry-run", action="store_true", help="required; never deploys or writes disks")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help=argparse.SUPPRESS)
    parser.add_argument("--plan-output", metavar="PATH", help="write draft plan; stdout is used otherwise")
    parser.add_argument("--quiet", action="store_true", help="suppress human summary")

    install = parser.add_argument_group(
        "install path",
        "Plan a disk layout and the steps that would install onto it. Dry run "
        "unless --execute is given together with --acknowledge-disk.",
    )
    install.add_argument("--install", action="store_true",
                         help="plan disk layout and install steps for --target-disk")
    install.add_argument("--target-disk", metavar="PATH", help="whole block device, e.g. /dev/nvme0n1")
    install.add_argument("--target-size-bytes", type=int,
                         help="size reported for the disk; drift above 2% is refused")
    install.add_argument("--firmware", choices=("uefi", "bios"), default="uefi")
    install.add_argument("--filesystem", choices=("ext4", "btrfs", "xfs"), default="ext4")
    install.add_argument("--mount-point", default="/mnt")
    install.add_argument("--system-file", default="systems/desktop.scm",
                         help="Guix system file handed to guix system init")
    install.add_argument("--execute", action="store_true",
                         help="actually run the steps; requires --acknowledge-disk")
    install.add_argument("--acknowledge-disk", metavar="PATH",
                         help="must repeat --target-disk exactly; there is no --yes")
    return parser


def _load_json(path: Path) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, f"cannot read report: {exc}"
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, raw, f"invalid report JSON: {exc}"
    if not isinstance(value, dict):
        return None, raw, "invalid report JSON: top-level value must be an object"
    return value, raw, None




def _safe_plan_output_path(
    output_value: str,
    report_path: Path,
    schema_path: Path,
) -> tuple[Path | None, str | None]:
    """Resolve a regular-file destination without aliasing inputs or device nodes."""
    requested = Path(output_value)
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        return None, f"plan output parent is unavailable: {exc}"
    if not parent.is_dir():
        return None, "plan output parent is not a directory"

    destination = parent / requested.name
    for source in (report_path, schema_path):
        try:
            source_resolved = source.resolve(strict=True)
        except OSError as exc:
            return None, f"cannot resolve protected input path {source}: {exc}"
        if destination == source_resolved:
            return None, "plan output must not overwrite the report or schema input"
        if destination.exists():
            try:
                if os.path.samefile(destination, source):
                    return None, "plan output must not alias the report or schema input"
            except OSError as exc:
                return None, f"cannot verify plan output identity: {exc}"

    try:
        destination_mode = destination.lstat().st_mode
    except FileNotFoundError:
        destination_mode = None
    except OSError as exc:
        return None, f"cannot inspect plan output destination: {exc}"

    if destination_mode is not None and not stat.S_ISREG(destination_mode):
        return None, "plan output must be a regular file; symlinks and device nodes are refused"

    for special_root in (Path("/dev"), Path("/proc"), Path("/sys")):
        try:
            special = special_root.resolve(strict=True)
        except OSError:
            continue
        if destination == special or special in destination.parents:
            return None, f"plan output is not allowed under {special}"

    return destination, None


def _write_plan_atomically(destination: Path, rendered: str) -> None:
    """Write a same-directory temporary file and atomically replace the destination."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _run_install(args: argparse.Namespace) -> int:
    """Plan, then optionally run, the disk path. Dry run is the default."""
    from wsm_install.executor import ExecutorError, execute
    from wsm_install.install_steps import backend_command, plan_steps, render
    from wsm_install.partition import Disk, Refused, plan as plan_layout

    if not args.target_disk:
        print("wsm-install: --install requires --target-disk", file=sys.stderr)
        return 2
    if args.target_size_bytes is None:
        print(
            "wsm-install: --install requires --target-size-bytes; the size is how a "
            "replaced disk is detected, so it cannot be guessed",
            file=sys.stderr,
        )
        return 2

    disk = Disk(
        path=args.target_disk,
        size_bytes=args.target_size_bytes,
        has_existing_data=True,
    )
    try:
        layout = plan_layout(
            disk,
            args.firmware,
            acknowledgement=args.acknowledge_disk,
            expected_size_bytes=args.target_size_bytes,
        )
        steps = plan_steps(layout, args.filesystem, args.mount_point)
        command = backend_command(layout, args.system_file, args.mount_point)
    except Refused as exc:
        print(f"wsm-install: {exc.code}: {exc.message}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(render(steps, command), file=sys.stderr)

    try:
        results = execute(
            steps,
            disk=disk.path,
            acknowledgement=args.acknowledge_disk,
            dry_run=not args.execute,
        )
    except ExecutorError as exc:
        print(f"wsm-install: {exc.code}: {exc.message}", file=sys.stderr)
        return 1

    print(json.dumps(
        {
            "mode": "execute" if args.execute else "dry-run",
            "disk": disk.path,
            "firmware": args.firmware,
            "filesystem": args.filesystem,
            "steps": [result.as_dict() for result in results],
            "handoff": command,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.preflight:
        parser.error("--preflight is required")
    if not args.dry_run:
        parser.error("--dry-run is required; this prototype never performs deployment")

    report, raw, error = _load_json(Path(args.report))
    if error:
        print(f"wsm-install: {error}", file=sys.stderr)
        return 2

    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"wsm-install: cannot load hardware report schema: {exc}", file=sys.stderr)
        return 2

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(report), key=lambda item: list(item.absolute_path))
    if errors:
        for item in errors[:20]:
            location = ".".join(str(part) for part in item.absolute_path) or "$"
            print(f"wsm-install: schema error at {location}: {item.message}", file=sys.stderr)
        if len(errors) > 20:
            print(f"wsm-install: {len(errors) - 20} additional schema errors omitted", file=sys.stderr)
        return 2

    if args.install:
        return _run_install(args)

    assert raw is not None
    plan, blockers, warnings = build_plan(report, raw, args.backend)
    if not args.quiet:
        print(summarize_report(report), file=sys.stderr)
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        for blocker in blockers:
            print(f"BLOCKED: {blocker}", file=sys.stderr)

    if blockers:
        print("wsm-install: no plan emitted because required critical evidence is unresolved", file=sys.stderr)
        return 3

    rendered = canonical_json(plan) + "\n"
    if args.plan_output:
        destination, path_error = _safe_plan_output_path(
            args.plan_output, Path(args.report), args.schema
        )
        if path_error:
            print(f"wsm-install: unsafe plan output: {path_error}", file=sys.stderr)
            return 2
        assert destination is not None
        try:
            _write_plan_atomically(destination, rendered)
        except OSError as exc:
            print(f"wsm-install: cannot write plan: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
