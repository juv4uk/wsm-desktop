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
import threading
from pathlib import Path
from typing import Sequence


DISK_SIZE_RE = re.compile(r"^([1-9][0-9]*)(M|G|T)$", re.IGNORECASE)
MIN_DISK_MIB = 256
MAX_DISK_MIB = 64 * 1024
MIN_MEMORY_MIB = 256
MAX_MEMORY_MIB = 16 * 1024
MIN_CPUS = 1
MAX_CPUS = 16
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 30 * 60
MAX_SERIAL_CAPTURE_BYTES = 1024 * 1024
MAX_STDERR_CAPTURE_BYTES = 256 * 1024
MAX_BOOT_MARKER_BYTES = 4096
CAPTURE_CHUNK_BYTES = 64 * 1024


def parse_disk_size_mib(value: str) -> int:
    """Parse a QEMU disk-size value and return its size in MiB."""
    match = DISK_SIZE_RE.fullmatch(value)
    if not match:
        raise ValueError("disk size must be an integer followed by M, G, or T")
    amount = int(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"M": 1, "G": 1024, "T": 1024 * 1024}[unit]
    size_mib = amount * multiplier
    if not MIN_DISK_MIB <= size_mib <= MAX_DISK_MIB:
        raise ValueError(
            f"disk size must be between {MIN_DISK_MIB}M and {MAX_DISK_MIB // 1024}G"
        )
    return size_mib


def validate_limits(timeout_seconds: int, memory_mib: int, cpus: int, disk_size: str) -> None:
    """Reject resource requests outside the harness's explicit safety policy."""
    if not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    if not MIN_MEMORY_MIB <= memory_mib <= MAX_MEMORY_MIB:
        raise ValueError(
            f"memory must be between {MIN_MEMORY_MIB} and {MAX_MEMORY_MIB} MiB"
        )
    if not MIN_CPUS <= cpus <= MAX_CPUS:
        raise ValueError(f"CPU count must be between {MIN_CPUS} and {MAX_CPUS}")
    parse_disk_size_mib(disk_size)


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


def _capture_stream(
    stream,
    max_bytes: int,
    marker_bytes: bytes | None = None,
) -> tuple[bytes, bool, bool, int]:
    """Consume a binary stream while retaining only a bounded tail.

    Marker detection scans the complete stream, including matches split across
    read boundaries. Memory use is bounded by max_bytes, one read chunk, and
    the marker overlap.
    """
    if max_bytes < 1:
        raise ValueError("capture limit must be positive")

    tail = bytearray()
    marker_seen = False
    overlap = b""
    total_bytes = 0

    while True:
        chunk = stream.read(CAPTURE_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)

        if marker_bytes and not marker_seen:
            scan = overlap + chunk
            marker_seen = marker_bytes in scan
            keep = len(marker_bytes) - 1
            overlap = scan[-keep:] if keep else b""

        tail.extend(chunk)
        excess = len(tail) - max_bytes
        if excess > 0:
            del tail[:excess]

    return bytes(tail), total_bytes > max_bytes, marker_seen, total_bytes


def _run_qemu_with_bounded_capture(
    command: list[str],
    timeout_seconds: int,
    marker_bytes: bytes | None,
) -> tuple[bool, int | None, tuple[bytes, bool, bool, int], tuple[bytes, bool, bool, int]]:
    """Run QEMU while concurrently draining both pipes into bounded tails."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise OSError("QEMU stdout/stderr pipes could not be opened")

    captured: dict[str, tuple[bytes, bool, bool, int]] = {}
    reader_errors: list[BaseException] = []

    def consume(name: str, stream, limit: int, marker: bytes | None = None) -> None:
        try:
            captured[name] = _capture_stream(stream, limit, marker)
        except BaseException as exc:
            reader_errors.append(exc)

    readers = [
        threading.Thread(
            target=consume,
            args=("serial", process.stdout, MAX_SERIAL_CAPTURE_BYTES, marker_bytes),
            name="wsm-qemu-serial-capture",
            daemon=True,
        ),
        threading.Thread(
            target=consume,
            args=("stderr", process.stderr, MAX_STDERR_CAPTURE_BYTES),
            name="wsm-qemu-stderr-capture",
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            process.kill()
        except ProcessLookupError:
            pass
        returncode = process.wait()

    for reader in readers:
        reader.join()
    process.stdout.close()
    process.stderr.close()

    if reader_errors:
        raise OSError(f"failed to capture QEMU output: {reader_errors[0]}") from reader_errors[0]
    if "serial" not in captured or "stderr" not in captured:
        raise OSError("QEMU output capture did not complete")

    return (
        timed_out,
        None if timed_out else returncode,
        captured["serial"],
        captured["stderr"],
    )


def build_qemu_command(
    qemu: str,
    iso: Path,
    qcow2: Path,
    memory_mib: int,
    cpus: int,
) -> list[str]:
    """Build isolated QEMU arguments using JSON blockdev nodes and stdio serial."""
    file_node = json.dumps({
        "driver": "file",
        "filename": str(qcow2),
        "node-name": "wsm-disk-file",
    }, separators=(",", ":"))
    qcow2_node = json.dumps({
        "driver": "qcow2",
        "file": "wsm-disk-file",
        "node-name": "wsm-disk",
    }, separators=(",", ":"))
    return [
        qemu,
        "-machine", "q35,accel=tcg",
        "-m", str(memory_mib),
        "-smp", str(cpus),
        "-cdrom", str(iso),
        "-blockdev", file_node,
        "-blockdev", qcow2_node,
        "-device", "virtio-blk-pci,drive=wsm-disk",
        "-boot", "order=d",
        "-display", "none",
        "-serial", "stdio",
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
    try:
        validate_limits(args.timeout_seconds, args.memory_mib, args.cpus, args.disk_size)
    except ValueError as exc:
        print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
        return 2
    try:
        iso = validate_iso(args.iso)
    except ValueError as exc:
        print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
        return 2
    if args.boot_marker and len(args.boot_marker.encode("utf-8")) > MAX_BOOT_MARKER_BYTES:
        print(
            f"qemu-boot-smoke: boot marker exceeds {MAX_BOOT_MARKER_BYTES} UTF-8 bytes",
            file=sys.stderr,
        )
        return 2

    qemu = shutil.which("qemu-system-x86_64") or "qemu-system-x86_64"
    qemu_img = shutil.which("qemu-img") or "qemu-img"

    with tempfile.TemporaryDirectory(prefix="wsm-qemu-smoke-") as temporary:
        work = Path(temporary).resolve()
        qcow2 = work / "disposable.qcow2"
        command = build_qemu_command(qemu, iso, qcow2, args.memory_mib, args.cpus)

        if args.dry_run:
            print(json.dumps({
                "mode": "dry-run",
                "iso": str(iso),
                "temporary_directory": str(work),
                "qcow2_path": str(qcow2),
                "qemu_command": command,
                "resource_limits": {
                    "disk_size_mib": parse_disk_size_mib(args.disk_size),
                    "memory_mib": args.memory_mib,
                    "cpus": args.cpus,
                    "timeout_seconds": args.timeout_seconds,
                },
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

        marker_bytes = args.boot_marker.encode("utf-8") if args.boot_marker else None
        try:
            timed_out, qemu_returncode, serial_capture, stderr_capture = (
                _run_qemu_with_bounded_capture(
                    command,
                    args.timeout_seconds,
                    marker_bytes,
                )
            )
        except OSError as exc:
            print(f"qemu-boot-smoke: cannot run/capture QEMU: {exc}", file=sys.stderr)
            return 3

        serial_bytes_tail, serial_truncated, marker_seen, serial_total_bytes = serial_capture
        stderr_bytes_tail, stderr_truncated, _, stderr_total_bytes = stderr_capture
        serial = serial_bytes_tail.decode("utf-8", errors="replace")
        qemu_error = stderr_bytes_tail.decode("utf-8", errors="replace").strip() or None
        result = {
            "mode": "qemu-boot-smoke",
            "iso": str(iso),
            "boot_confirmed": marker_seen,
            "boot_marker_configured": bool(args.boot_marker),
            "qemu_timed_out": timed_out,
            "qemu_returncode": qemu_returncode,
            "serial_output_tail": serial[-4000:],
            "serial_output_truncated": serial_truncated,
            "serial_output_bytes": serial_total_bytes,
            "qemu_error": qemu_error,
            "qemu_error_truncated": stderr_truncated,
            "qemu_error_bytes": stderr_total_bytes,
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
