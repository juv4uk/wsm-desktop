# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a disposable, offline QEMU boot smoke test for a supplied live ISO.

This is a boot smoke test only. It does not claim that wsm-install ran inside
the guest; that requires a guest image containing the CLI and a defined
guest-side invocation channel.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


DISK_SIZE_RE = re.compile(r"^[1-9][0-9]*(?:M|G|T)$", re.IGNORECASE)


def validate_iso(path: Path) -> Path:
    """Accept only an existing regular ISO file, never a device or directory."""
    if path.is_symlink():
        raise ValueError("ISO path must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot resolve ISO path: {exc}") from exc
    if not resolved.is_file():
        raise ValueError("ISO path must be a regular file")
    if resolved.stat().st_size == 0:
        raise ValueError("ISO file is empty")
    return resolved


def build_qemu_command(
    qemu: str,
    iso: Path,
    qcow2: Path,
    serial_log: Path,
    memory_mib: int,
    cpus: int,
) -> list[str]:
    """Build a deliberately isolated QEMU command with no host device passthrough."""
    return [
        qemu,
        "-machine", "q35,accel=tcg",
        "-m", str(memory_mib),
        "-smp", str(cpus),
        "-cdrom", str(iso),
        "-drive", f"file={qcow2},if=virtio,format=qcow2",
        "-boot", "order=d",
        "-display", "none",
        "-serial", f"file:{serial_log}",
        "-monitor", "none",
        "-nic", "none",
        "-no-reboot",
        "-no-shutdown",
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Boot a supplied live ISO in disposable, offline QEMU (boot smoke test only)."
    )
    parser.add_argument("--iso", required=True, type=Path, help="existing regular live ISO file")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--memory-mib", type=int, default=2048)
    parser.add_argument("--cpus", type=int, default=2)
    parser.add_argument("--disk-size", default="4G")
    parser.add_argument(
        "--boot-marker",
        help="literal text that must appear on the serial console to confirm boot",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the isolated QEMU command only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout_seconds < 1 or args.memory_mib < 256 or args.cpus < 1:
        print("qemu-boot-smoke: timeout, memory or CPU count is outside safe bounds", file=sys.stderr)
        return 2
    if not DISK_SIZE_RE.fullmatch(args.disk_size):
        print("qemu-boot-smoke: --disk-size must be a positive size such as 4G or 2048M", file=sys.stderr)
        return 2
    try:
        iso = validate_iso(args.iso)
    except ValueError as exc:
        print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
        return 2

    qemu = shutil.which("qemu-system-x86_64") or "qemu-system-x86_64"
    qemu_img = shutil.which("qemu-img") or "qemu-img"

    with tempfile.TemporaryDirectory(prefix="wsm-qemu-smoke-") as temporary:
        work = Path(temporary).resolve()
        qcow2 = work / "disposable.qcow2"
        serial_log = work / "serial.log"
        command = build_qemu_command(qemu, iso, qcow2, serial_log, args.memory_mib, args.cpus)

        if args.dry_run:
            print(json.dumps({
                "mode": "dry-run",
                "iso": str(iso),
                "temporary_directory": str(work),
                "qcow2_path": str(qcow2),
                "qemu_command": command,
                "host_device_passthrough": False,
                "network_enabled": False,
                "efi_variable_store": False,
                "guest_installer_execution": False,
            }, sort_keys=True, indent=2))
            return 0

        if not shutil.which("qemu-system-x86_64") or not shutil.which("qemu-img"):
            print("qemu-boot-smoke: qemu-system-x86_64 and qemu-img must be installed", file=sys.stderr)
            return 2

        try:
            subprocess.run(
                [qemu_img, "create", "-f", "qcow2", str(qcow2), args.disk_size],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"qemu-boot-smoke: cannot create disposable qcow2 image: {exc}", file=sys.stderr)
            return 3

        timed_out = False
        qemu_error: str | None = None
        try:
            completed = subprocess.run(
                command,
                check=False,
                timeout=args.timeout_seconds,
                capture_output=True,
                text=True,
            )
            qemu_returncode = completed.returncode
            qemu_error = completed.stderr.strip() or None
        except subprocess.TimeoutExpired:
            timed_out = True
            qemu_returncode = None
        except OSError as exc:
            print(f"qemu-boot-smoke: cannot start QEMU: {exc}", file=sys.stderr)
            return 3

        serial = serial_log.read_text(encoding="utf-8", errors="replace") if serial_log.exists() else ""
        marker_seen = bool(args.boot_marker and args.boot_marker in serial)
        result = {
            "mode": "qemu-boot-smoke",
            "iso": str(iso),
            "boot_confirmed": marker_seen,
            "boot_marker_configured": bool(args.boot_marker),
            "qemu_timed_out": timed_out,
            "qemu_returncode": qemu_returncode,
            "serial_output_tail": serial[-4000:],
            "qemu_error": qemu_error,
            "host_device_passthrough": False,
            "network_enabled": False,
            "efi_variable_store": False,
            "guest_installer_execution": False,
        }
        print(json.dumps(result, sort_keys=True, indent=2))
        if marker_seen:
            return 0
        if not args.boot_marker:
            print("qemu-boot-smoke: boot not confirmed; provide --boot-marker from the guest serial console", file=sys.stderr)
        else:
            print("qemu-boot-smoke: configured boot marker was not observed", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
