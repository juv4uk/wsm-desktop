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
from .profile import EvidenceUnavailable, load as load_profile_evidence

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
        "--backend", required=True, choices=("guix",),
        help="only supported first-preview backend: guix -> guix-system",
    )
    parser.add_argument("--dry-run", action="store_true", help="required; never deploys or writes disks")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help=argparse.SUPPRESS)
    parser.add_argument(
        "--profile-evidence",
        type=Path,
        metavar="PATH",
        help="optional evidence.json; its profile source and artifact bytes are checked read-only",
    )
    parser.add_argument("--plan-output", metavar="PATH", help="write draft plan; stdout is used otherwise")
    parser.add_argument("--quiet", action="store_true", help="suppress human summary")
    parser.add_argument(
        "--admission",
        action="store_true",
        help="also report what APPLY would require, step by step; writes nothing",
    )

    install = parser.add_argument_group(
        "install path",
        "Plan a disk layout and show the steps that would install onto it. "
        "Preview-only: real APPLY is disabled across all installer frontends.",
    )
    install.add_argument("--install", action="store_true",
                         help="plan disk layout and install steps for --target-disk")
    install.add_argument("--target-disk", metavar="PATH", help="whole block device, e.g. /dev/nvme0n1")
    install.add_argument("--target-size-bytes", type=int,
                         help="size reported for the disk; drift above 2 percent is refused")
    install.add_argument("--firmware", choices=("uefi", "bios"), default="uefi")
    install.add_argument("--filesystem", choices=("ext4",), default="ext4", help="root filesystem declared by systems/desktop.scm")
    install.add_argument("--mount-point", default="/mnt")
    install.add_argument("--system-file", default="systems/desktop.scm",
                         help="Guix system file handed to guix system init")
    install.add_argument("--execute", action="store_true",
                         help="disabled; real APPLY requires a separately reviewed target-bound executor")
    install.add_argument("--guided", action="store_true",
                         help="choose a target and show a read-only preview in the console")
    install.add_argument("--classify", action="store_true",
                         help="print a read-only evidence summary; does not decide install readiness")
    install.add_argument("--check-env", action="store_true",
                         help="verify this machine can install at all, then stop")
    install.add_argument("--write-plan", metavar="PATH",
                         help="write a read-only preview plan as JSON; the agent cannot APPLY it")
    install.add_argument("--tui", action="store_true",
                         help="pseudo-graphical read-only preview: full screen, arrow keys, Enter")
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
    extra_protected_paths: tuple[Path, ...] = (),
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
    for source in (report_path, schema_path, *extra_protected_paths):
        try:
            source_resolved = source.resolve(strict=True)
        except OSError as exc:
            return None, f"cannot resolve protected input path {source}: {exc}"
        if destination == source_resolved:
            if source in extra_protected_paths:
                return None, "plan output must not overwrite a protected input"
            return None, "plan output must not overwrite the report or schema input"
        if destination.exists():
            try:
                if os.path.samefile(destination, source):
                    if source in extra_protected_paths:
                        return None, "plan output must not alias a protected input"
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


class _Console:
    """Minimal console adapter: stdout for writing, stdin for reading."""

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def read(self, prompt: str) -> str:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            return ""
        return line.rstrip("\n")


def _tool_prefixes_for_running_system() -> tuple[str, ...] | None:
    """Use the Guix profile paths in the live image; keep host preview FHS-only.

    The presence of the system profile is an explicit filesystem fact, not a
    PATH lookup. In a booted WSM Guix image the planner and guest closure probe
    therefore resolve the same two prefixes. On a foreign development host the
    historical fixed FHS preview paths remain available.
    """
    from wsm_install.tools import GUIX_PROFILE_PREFIXES

    if any(Path(prefix).is_dir() for prefix in GUIX_PROFILE_PREFIXES):
        return GUIX_PROFILE_PREFIXES
    return None


def _tool_paths_for_running_system() -> tuple[str, ...] | None:
    """Return the exact profile paths that both planner and preflight will use."""
    prefixes = _tool_prefixes_for_running_system()
    if prefixes is None:
        return None

    from wsm_install.tool_map import TOOLS
    from wsm_install.tools import resolve

    # Missing tools still need an expected absolute candidate so preflight fails
    # against the image profile rather than accidentally finding a host /usr copy.
    return tuple(
        resolve(name, prefixes=prefixes) or f"{prefixes[0]}/{name}"
        for name in TOOLS
    )


def _run_env_check(args: argparse.Namespace) -> int:
    """Check the environment before a disk is touched."""
    from wsm_install.preflight_env import run as run_env_check

    result = run_env_check(
        mount_point=Path(args.mount_point),
        system_file=Path(args.system_file),
        report=Path(args.report) if args.report else None,
        paths=_tool_paths_for_running_system(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["overall"] == "fail" else 0


def _hardware_note(args: argparse.Namespace) -> str:
    """One line about what the hardware report found, for the chooser screen."""
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return "hardware report could not be read; the install is unverified"
    devices = report.get("devices") or []
    return (
        f"report {report.get('report_id', 'unknown')}, "
        f"{len(devices)} device(s), "
        f"{len(report.get('warnings') or [])} warning(s)"
    )


def _installer_preview(args: argparse.Namespace, report: dict[str, Any], report_bytes: bytes):
    """Build the callback the guided and TUI frontends call on a chosen disk.

    The report and its raw bytes are captured here rather than re-read: the
    frontends only pick a disk, and re-loading the report inside a callback would
    let the plan be built from different bytes than the ones that passed schema
    validation in main().
    """

    def preview(disk_path: str, size: int, firmware: str) -> int:
        return _run_install(argparse.Namespace(
            target_disk=disk_path,
            target_size_bytes=size,
            firmware=firmware,
            filesystem=args.filesystem,
            mount_point=args.mount_point,
            system_file=args.system_file,
            acknowledge_disk=disk_path,
            execute=False,
            quiet=True,
            write_plan=None,
            backend=args.backend,
        ), report, report_bytes)

    return preview


def _run_tui(args: argparse.Namespace, report: dict[str, Any], report_bytes: bytes) -> int:
    """Pseudo-graphical flow; preview only until a reviewed APPLY exists."""
    from wsm_install.guided import list_disks
    from wsm_install.tui import TerminalScreen, run_tui

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "wsm-install: no terminal for pseudo-graphics; using the console preview",
            file=sys.stderr,
        )
        return _run_guided(args, report, report_bytes)

    preview = _installer_preview(args, report, report_bytes)
    return run_tui(
        TerminalScreen(),
        list_disks(Path("/sys/block")),
        preview,
        _hardware_note(args),
    )


def _run_guided(args: argparse.Namespace, report: dict[str, Any], report_bytes: bytes) -> int:
    """Console flow: choose a disk and show a read-only preview."""
    from wsm_install.guided import list_disks, run_guided

    preview = _installer_preview(args, report, report_bytes)
    return run_guided(
        _Console(),
        list_disks(Path("/sys/block")),
        preview,
        _hardware_note(args),
    )


def _run_classification(report: dict[str, Any]) -> dict:
    """Summarize report evidence only; scenario policy is evaluated elsewhere."""
    from wsm_install.classification import classify

    return classify(report)


def _run_install(
    args: argparse.Namespace,
    report: dict[str, Any],
    report_bytes: bytes,
) -> int:
    """Build and render a disk plan; real APPLY is disabled."""
    if args.execute:
        print(
            "wsm-install: execute.apply-disabled: real APPLY is disabled across all "
            "frontends until target identity and digest-bound consent are implemented",
            file=sys.stderr,
        )
        return 2

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

    # A subsystem summary is diagnostic, not an installation policy. Reuse the
    # existing report planner for its explicit critical-role and firmware
    # blockers; do not derive stop/warn/proceed from a global subsystem label.
    _plan, blockers, warnings = build_plan(report, report_bytes, args.backend)
    if blockers:
        for blocker in blockers:
            print(f"wsm-install: plan.blocked: {blocker}", file=sys.stderr)
        print(
            "wsm-install: no preview plan emitted because required critical evidence is unresolved",
            file=sys.stderr,
        )
        return 3
    if not args.quiet:
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)

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
        steps = plan_steps(
            layout,
            args.filesystem,
            args.mount_point,
            tool_prefixes=_tool_prefixes_for_running_system(),
        )
        command = backend_command(layout, args.system_file, args.mount_point)
    except Refused as exc:
        print(f"wsm-install: {exc.code}: {exc.message}", file=sys.stderr)
        return 2

    if args.write_plan:
        # A preview artifact is still a file write. Refuse device nodes, pseudo
        # filesystems, symlinks, and aliases of the report/schema inputs.
        destination, error = _safe_plan_output_path(
            args.write_plan,
            Path(args.report),
            Path(args.schema),
        )
        if error or destination is None:
            print(
                f"wsm-install: write-plan.refused: {error or 'invalid destination'}",
                file=sys.stderr,
            )
            return 2
        rendered = json.dumps({
            "schema": "wsm-install-plan/1",
            "disk": disk.path,
            "firmware": args.firmware,
            "filesystem": args.filesystem,
            "mount_point": args.mount_point,
            "handoff": command,
            "steps": [
                {
                    "command": step.command,
                    "purpose": step.purpose,
                    "destructive": step.destructive,
                }
                for step in steps
            ],
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            _write_plan_atomically(destination, rendered)
        except OSError as exc:
            print(f"wsm-install: write-plan.failed: {exc}", file=sys.stderr)
            return 2
        print(
            f"wsm-install: preview plan written to {destination}; APPLY disabled",
            file=sys.stderr,
        )
        return 0

    if not args.quiet:
        print(render(steps, command), file=sys.stderr)

    try:
        results = execute(
            steps,
            disk=disk.path,
            dry_run=True,
        )
    except ExecutorError as exc:
        print(f"wsm-install: {exc.code}: {exc.message}", file=sys.stderr)
        return 1

    admission = None
    if args.admission:
        admission = _admission_report(steps, disk.path)

    print(json.dumps(
        {
            "mode": "dry-run",
            "target_size_source": "user-supplied planning estimate; not read from the block device",
            "disk": disk.path,
            "firmware": args.firmware,
            "filesystem": args.filesystem,
            "steps": [result.as_dict() for result in results],
            "handoff": command,
            **({"admission": admission} if admission is not None else {}),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


def _admission_report(steps: list, disk_path: str) -> dict:
    """What APPLY would require, from the real read-only observers.

    No consent is offered here on purpose: a preview is not a prompt, so every
    destructive step comes back refused with `consent.missing`. That is the honest
    answer to "what would stop this", and it keeps the report from looking like an
    approval nobody gave.
    """
    from wsm_install.admission import admit
    from wsm_install.disk_identity import IdentityError, capture
    from wsm_install.observers import FilesystemObserver, SysfsDiskObserver

    disk_observer = SysfsDiskObserver()
    try:
        expected = capture(disk_observer, disk_path)
    except IdentityError as exc:
        return {"status": "refused", "reason": f"{exc.code}: {exc.message}", "steps": []}

    report = admit(
        steps,
        disk_path,
        expected_identity=expected,
        disk_observer=disk_observer,
        observer=FilesystemObserver(),
        consent_for=None,
    )
    return {
        "status": report.status,
        "reason": report.reason,
        "plan_digest": report.plan_digest,
        "steps": [
            {
                "index": step.index,
                "destructive": step.destructive,
                "status": step.status,
                "reason": step.reason,
                "step_digest": step.step_digest,
            }
            for step in report.steps
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.execute:
        print(
            "wsm-install: execute.apply-disabled: --execute is disabled before "
            "frontend selection or report processing",
            file=sys.stderr,
        )
        return 2
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

    if args.profile_evidence is not None and (
        args.classify or args.check_env or args.install or args.guided or args.tui
    ):
        print(
            "wsm-install: --profile-evidence is accepted only by the read-only preflight planner",
            file=sys.stderr,
        )
        return 2

    if args.classify:
        print(json.dumps(_run_classification(report), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.check_env:
        return _run_env_check(args)
    if args.tui:
        return _run_tui(args, report, raw)
    if args.guided:
        return _run_guided(args, report, raw)
    if args.install:
        assert raw is not None
        return _run_install(args, report, raw)

    assert raw is not None
    profile_evidence = None
    profile_evidence_root = None
    if args.profile_evidence is not None:
        try:
            profile_evidence = load_profile_evidence(args.profile_evidence)
        except EvidenceUnavailable as exc:
            print(f"wsm-install: invalid profile evidence: {exc}", file=sys.stderr)
            return 2
        profile_evidence_root = args.profile_evidence.parent

    plan, blockers, warnings = build_plan(
        report,
        raw,
        args.backend,
        profile_evidence,
        profile_evidence_root,
    )
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
        protected_profile_inputs: tuple[Path, ...] = ()
        if (
            args.profile_evidence is not None
            and profile_evidence is not None
            and profile_evidence_root is not None
        ):
            raw_artifacts = profile_evidence.get("artifacts")
            artifact_paths = (
                tuple(
                    profile_evidence_root / item["path"]
                    for item in raw_artifacts
                    if isinstance(item, dict) and isinstance(item.get("path"), str)
                )
                if isinstance(raw_artifacts, list) else ()
            )
            protected_profile_inputs = (
                args.profile_evidence,
                profile_evidence_root / "profile.scm",
                *artifact_paths,
            )

        destination, path_error = _safe_plan_output_path(
            args.plan_output,
            Path(args.report),
            args.schema,
            protected_profile_inputs,
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
