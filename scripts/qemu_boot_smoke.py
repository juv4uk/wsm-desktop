# SPDX-License-Identifier: LicenseRef-Volnist
"""Run a disposable, offline QEMU boot smoke test for a supplied live ISO.

This is a boot smoke test only. It does not claim that wsm-install ran inside
the guest; that requires a guest image containing the CLI and a defined
guest-side invocation channel.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


DISK_SIZE_RE = re.compile(r"^([1-9][0-9]*)(M|G|T)$", re.IGNORECASE)
MIN_DISK_MIB = 256
MAX_DISK_MIB = 64 * 1024
MIN_MEMORY_MIB = 256
MAX_MEMORY_MIB = 16 * 1024
MIN_CPUS = 1
MAX_CPUS = 16
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 30 * 60

# Keep capture bounded independently of the JSON presentation tail.
MAX_SERIAL_CAPTURE_BYTES = 1024 * 1024
MAX_STDERR_CAPTURE_BYTES = 256 * 1024
MAX_SERIAL_OUTPUT_TAIL_CHARS = 4000
MAX_BOOT_MARKER_BYTES = 1024
PROCESS_READ_CHUNK_BYTES = 64 * 1024
POST_KILL_DRAIN_SECONDS = 0.5


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int | None
    timed_out: bool
    stdout_tail: bytes
    stderr_tail: bytes
    stdout_bytes_seen: int
    stderr_bytes_seen: int
    stdout_truncated: bool
    stderr_truncated: bool
    marker_seen: bool


def _append_bounded_tail(target: bytearray, chunk: bytes, limit: int) -> None:
    """Append bytes while retaining no more than limit bytes."""
    if len(chunk) >= limit:
        target[:] = chunk[-limit:]
        return
    overflow = len(target) + len(chunk) - limit
    if overflow > 0:
        del target[:overflow]
    target.extend(chunk)


def run_bounded_process(
    command: list[str],
    *,
    timeout_seconds: float,
    marker: str | None,
    popen_factory: Callable[..., Any] | None = None,
    max_stdout_bytes: int = MAX_SERIAL_CAPTURE_BYTES,
    max_stderr_bytes: int = MAX_STDERR_CAPTURE_BYTES,
    read_chunk_bytes: int = PROCESS_READ_CHUNK_BYTES,
) -> BoundedProcessResult:
    """Run a child while streaming stdout/stderr into fixed-size tail buffers.

    Marker detection scans the complete serial byte stream, independently of
    the retained tail. A short overlap preserves markers split across reads.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_stdout_bytes < 1 or max_stderr_bytes < 1 or read_chunk_bytes < 1:
        raise ValueError("capture limits and read chunk size must be positive")

    marker_bytes = marker.encode("utf-8") if marker else b""
    if len(marker_bytes) > MAX_BOOT_MARKER_BYTES:
        raise ValueError(
            f"boot marker must be no more than {MAX_BOOT_MARKER_BYTES} UTF-8 bytes"
        )

    factory = popen_factory or subprocess.Popen
    process = factory(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        close_fds=True,
    )
    if process.stdout is None or process.stderr is None:
        try:
            process.kill()
        finally:
            process.wait()
        raise OSError("child process pipes were not created")

    selector = selectors.DefaultSelector()
    stdout_tail = bytearray()
    stderr_tail = bytearray()
    stdout_bytes_seen = 0
    stderr_bytes_seen = 0
    marker_seen = False
    marker_overlap = b""
    timed_out = False
    kill_drain_deadline: float | None = None
    streams = (process.stdout, process.stderr)

    try:
        for stream, label in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)

        deadline = time.monotonic() + timeout_seconds
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            if not timed_out and now >= deadline:
                timed_out = True
                kill_drain_deadline = now + POST_KILL_DRAIN_SECONDS
                try:
                    process.kill()
                except OSError:
                    pass

            if timed_out and kill_drain_deadline is not None and now >= kill_drain_deadline:
                for key in list(selector.get_map().values()):
                    stream = key.fileobj
                    selector.unregister(stream)
                    stream.close()
                break

            if selector.get_map():
                wait_for = 0.1
                if not timed_out:
                    wait_for = min(wait_for, max(0.0, deadline - now))
                elif kill_drain_deadline is not None:
                    wait_for = min(wait_for, max(0.0, kill_drain_deadline - now))
                events = selector.select(wait_for)
            else:
                time.sleep(0.02)
                events = ()

            for key, _ in events:
                stream = key.fileobj
                try:
                    chunk = os.read(key.fd, read_chunk_bytes)
                except BlockingIOError:
                    continue

                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue

                if key.data == "stdout":
                    stdout_bytes_seen += len(chunk)
                    _append_bounded_tail(stdout_tail, chunk, max_stdout_bytes)
                    if marker_bytes and not marker_seen:
                        candidate = marker_overlap + chunk
                        marker_seen = marker_bytes in candidate
                        overlap_size = max(0, len(marker_bytes) - 1)
                        marker_overlap = candidate[-overlap_size:] if overlap_size else b""
                else:
                    stderr_bytes_seen += len(chunk)
                    _append_bounded_tail(stderr_tail, chunk, max_stderr_bytes)

        try:
            returncode = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            returncode = process.wait(timeout=1.0)

        return BoundedProcessResult(
            returncode=returncode,
            timed_out=timed_out,
            stdout_tail=bytes(stdout_tail),
            stderr_tail=bytes(stderr_tail),
            stdout_bytes_seen=stdout_bytes_seen,
            stderr_bytes_seen=stderr_bytes_seen,
            stdout_truncated=stdout_bytes_seen > max_stdout_bytes,
            stderr_truncated=stderr_bytes_seen > max_stderr_bytes,
            marker_seen=marker_seen,
        )
    except BaseException:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    finally:
        selector.close()
        for stream in streams:
            if stream is not None and not stream.closed:
                stream.close()


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

def validate_ovmf_image(path: Path, label: str) -> Path:
    """Accept a non-empty regular OVMF image, never a symlink or device."""
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot resolve {label}: {exc}") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    if resolved.stat().st_size == 0:
        raise ValueError(f"{label} is empty")
    return resolved


def build_qemu_command(
    qemu: str,
    iso: Path,
    qcow2: Path,
    memory_mib: int,
    cpus: int,
    firmware: str = "bios",
    ovmf_code: Path | None = None,
    ovmf_vars: Path | None = None,
) -> list[str]:
    """Build isolated QEMU arguments using JSON blockdev nodes and stdio serial.

    ``firmware="uefi"`` maps OVMF_CODE read-only at pflash unit 0 and a
    private copy of the separate OVMF_VARS template writable at unit 1. The
    host templates are never mapped writable or modified. The acceptance for
    the live image requires both modes:
    a BIOS-only boot proves nothing about UEFI machines.
    """
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
    firmware_args: list[str] = []
    if firmware == "uefi":
        if ovmf_code is None or ovmf_vars is None:
            raise ValueError("uefi boot needs separate OVMF CODE and VARS images")
        if ovmf_code.resolve() == ovmf_vars.resolve():
            raise ValueError("OVMF CODE and VARS must be two different images")
        firmware_args = [
            "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={ovmf_code}",
            "-drive", f"if=pflash,format=raw,unit=1,file={ovmf_vars}",
        ]

    return [
        qemu,
        "-machine", "q35,accel=tcg",
        *firmware_args,
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
    parser.add_argument(
        "--firmware",
        choices=("bios", "uefi"),
        default="bios",
        help="boot firmware; uefi needs --ovmf-code and --ovmf-vars (acceptance requires both modes)",
    )
    parser.add_argument(
        "--ovmf-code",
        type=Path,
        help="read-only OVMF code image (e.g. /usr/share/OVMF/OVMF_CODE.fd)",
    )
    parser.add_argument(
        "--ovmf-vars",
        type=Path,
        help="separate OVMF variable-store template (e.g. /usr/share/OVMF/OVMF_VARS.fd)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the isolated QEMU command only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_limits(args.timeout_seconds, args.memory_mib, args.cpus, args.disk_size)
        if args.boot_marker and len(args.boot_marker.encode("utf-8")) > MAX_BOOT_MARKER_BYTES:
            raise ValueError(
                f"boot marker must be no more than {MAX_BOOT_MARKER_BYTES} UTF-8 bytes"
            )
    except (ValueError, UnicodeError) as exc:
        print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
        return 2
    try:
        iso = validate_iso(args.iso)
    except ValueError as exc:
        print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
        return 2

    qemu = shutil.which("qemu-system-x86_64") or "qemu-system-x86_64"
    qemu_img = shutil.which("qemu-img") or "qemu-img"

    ovmf_vars: Path | None = None
    ovmf_code_path: Path | None = None
    ovmf_vars_template: Path | None = None
    if args.firmware == "uefi":
        if args.ovmf_code is None or args.ovmf_vars is None:
            print(
                "qemu-boot-smoke: --firmware uefi requires both --ovmf-code and --ovmf-vars; "
                "a BIOS-only boot does not prove the UEFI path",
                file=sys.stderr,
            )
            return 2
        try:
            ovmf_code_path = validate_ovmf_image(args.ovmf_code, "OVMF CODE image")
            ovmf_vars_template = validate_ovmf_image(args.ovmf_vars, "OVMF VARS template")
        except ValueError as exc:
            print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
            return 2
        if ovmf_code_path == ovmf_vars_template:
            print("qemu-boot-smoke: OVMF CODE and VARS must be separate files", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="wsm-qemu-smoke-") as temporary:
        work = Path(temporary).resolve()
        qcow2 = work / "disposable.qcow2"
        if args.firmware == "uefi":
            # A writable copy per run: the guest must never write to the host's
            # variable store, and a fresh store keeps runs independent.
            ovmf_vars = work / "OVMF_VARS.fd"
            # Clone the VARS template for this run; never expose the host template writable.
            shutil.copyfile(ovmf_vars_template, ovmf_vars)
        command = build_qemu_command(
            qemu, iso, qcow2, args.memory_mib, args.cpus,
            firmware=args.firmware,
            ovmf_code=ovmf_code_path,
            ovmf_vars=ovmf_vars,
        )

        if args.dry_run:
            print(json.dumps({
                "mode": "dry-run",
                "iso": str(iso),
                "firmware": args.firmware,
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
                "host_efi_variables_modified": False,
                "guest_uefi_vars_writable": args.firmware == "uefi",
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

        try:
            # QEMU's chardev option parser is key/value based, not JSON.
            # Its stdio serial backend is captured via a pipe, never a temp file.
            captured = run_bounded_process(
                command,
                timeout_seconds=args.timeout_seconds,
                marker=args.boot_marker,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"qemu-boot-smoke: cannot start or capture QEMU: {exc}", file=sys.stderr)
            return 3

        serial = captured.stdout_tail.decode("utf-8", errors="replace")
        qemu_error = captured.stderr_tail.decode("utf-8", errors="replace").strip() or None
        marker_seen = captured.marker_seen
        result = {
            "mode": "qemu-boot-smoke",
            "iso": str(iso),
            "boot_confirmed": marker_seen,
            "boot_marker_configured": bool(args.boot_marker),
            "qemu_timed_out": captured.timed_out,
            "qemu_returncode": captured.returncode,
            "serial_output_tail": serial[-MAX_SERIAL_OUTPUT_TAIL_CHARS:],
            "serial_truncated": captured.stdout_truncated,
            "stderr_truncated": captured.stderr_truncated,
            "serial_bytes_seen": captured.stdout_bytes_seen,
            "stderr_bytes_seen": captured.stderr_bytes_seen,
            "qemu_error": qemu_error,
            "host_device_passthrough": False,
            "network_enabled": False,
            "host_efi_variables_modified": False,
            "guest_uefi_vars_writable": args.firmware == "uefi",
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
