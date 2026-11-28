# SPDX-License-Identifier: LicenseRef-Volnist
"""Run a disposable, offline QEMU boot smoke test for a supplied live ISO.

This is a boot smoke test only. It does not claim that wsm-install ran inside
the guest; that requires a guest image containing the CLI and a defined
guest-side invocation channel.

It can, however, read an answer the guest prints about itself. With
``--tool-closure-marker`` the harness looks in the captured serial stream for
the lines ``wsm_install.tool_closure`` emits inside the booted system — one per
allowlisted installer tool, naming its resolved path and whether it is a
regular executable file — and records the verdict in the evidence JSON as
``tool_closure``. A missing or non-executable tool then fails the boot
acceptance with exit code 5 instead of leaving a boot marker standing in for a
claim it never made. Without the flag the evidence says ``not-checked`` and no
verdict is implied.
"""

from __future__ import annotations

import argparse
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.tool_closure import (  # noqa: E402
    STATUS_FAIL,
    not_checked as not_checked_tool_closure,
    parse as parse_tool_closure,
)


DISK_SIZE_RE = re.compile(r"^([1-9][0-9]*)(M|G|T)$", re.IGNORECASE)
MIN_DISK_MIB = 256
MAX_DISK_MIB = 64 * 1024
MIN_MEMORY_MIB = 256
MAX_MEMORY_MIB = 16 * 1024
MIN_CPUS = 1
MAX_CPUS = 16
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 30 * 60

# Exit codes. 5 exists so that a boot which started but cannot prove its
# installer tools is distinguishable from a boot that never happened.
EXIT_BOOT_NOT_CONFIRMED = 4
EXIT_TOOL_CLOSURE_FAILED = 5

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
    second_marker_seen: bool = False


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
    second_marker: str | None = None,
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
    second_bytes = second_marker.encode("utf-8") if second_marker else b""
    if len(second_bytes) > MAX_BOOT_MARKER_BYTES:
        raise ValueError(
            f"installer marker must be no more than {MAX_BOOT_MARKER_BYTES} UTF-8 bytes"
        )
    second_seen = False
    second_overlap = b""
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
                    if second_bytes and not second_seen:
                        candidate = second_overlap + chunk
                        second_seen = second_bytes in candidate
                        overlap_size = max(0, len(second_bytes) - 1)
                        second_overlap = candidate[-overlap_size:] if overlap_size else b""
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
            second_marker_seen=second_seen,
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


def sha256_of(path: Path) -> str:
    """Hash the image in chunks; a 1 GiB ISO must not be read into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def tool_closure_evidence(serial: str, marker: str | None) -> dict[str, Any]:
    """The evidence value for the installer tools, as the guest reported them.

    `marker` is the caller opt-in. Without it the evidence says `not-checked` and
    claims nothing. With it, an empty report is a failure: a guest that said
    nothing has not proved anything, and silence must not read as success.
    """
    if not marker:
        return not_checked_tool_closure(None)
    verdict = parse_tool_closure(serial)
    evidence = verdict.as_dict()
    evidence["marker"] = marker
    evidence["guest_reported"] = verdict.reported_lines > 0
    return evidence


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
    """Accept a non-empty regular OVMF image; never follow a supplied symlink."""
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot resolve {label}: {exc}") from exc
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError(f"{label} must be a non-empty regular file")
    return resolved


def copy_ovmf_vars_template(template: Path, destination: Path) -> Path:
    """Copy a distinct OVMF VARS template into a private per-run writable file."""
    source = validate_ovmf_image(template, "OVMF variables template")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"refusing to overwrite OVMF variables destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if not destination.is_file() or destination.stat().st_size != source.stat().st_size:
        try:
            destination.unlink()
        except OSError:
            pass
        raise ValueError("private OVMF variables copy is incomplete")
    return destination


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

    ``firmware="uefi"`` adds a read-only OVMF code pflash plus a writable copy of
    the variable store, so the guest can set its own boot entries without
    touching the host's. The acceptance for the live image requires both modes:
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
            raise ValueError("uefi boot needs both an OVMF code image and a variables file")
        firmware_args = [
            "-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
            "-drive", f"if=pflash,format=raw,file={ovmf_vars}",
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
        "--installer-marker",
        help=(
            "marker the live system prints only after running the installer "
            "entrypoint; proves the image ships a working installer, which "
            "boot alone does not"
        ),
    )
    parser.add_argument(
        "--tool-closure-marker",
        help=(
            "read the guest's own report on the installer's tools out of the serial "
            "stream and fail the boot if any tool is missing or not executable; "
            "pass WSM_TOOL_CLOSURE for the marker wsm_install.tool_closure prints"
        ),
    )
    parser.add_argument(
        "--boot-marker",
        help="literal text that must appear on the serial console to confirm boot",
    )
    parser.add_argument(
        "--firmware",
        choices=("bios", "uefi"),
        default="bios",
        help="boot firmware; uefi needs --ovmf-code (acceptance requires both modes)",
    )
    parser.add_argument(
        "--ovmf-code",
        type=Path,
        help="read-only OVMF code image for --firmware uefi",
    )
    parser.add_argument(
        "--ovmf-vars",
        type=Path,
        help="separate OVMF variables template; a private writable copy is used for the guest",
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

    ovmf_code: Path | None = None
    ovmf_vars_template: Path | None = None
    ovmf_vars: Path | None = None
    if args.firmware == "uefi":
        if args.ovmf_code is None or args.ovmf_vars is None:
            print(
                "qemu-boot-smoke: --firmware uefi requires both --ovmf-code and "
                "--ovmf-vars; CODE and VARS must be separate files",
                file=sys.stderr,
            )
            return 2
        try:
            ovmf_code = validate_ovmf_image(args.ovmf_code, "OVMF code image")
            ovmf_vars_template = validate_ovmf_image(args.ovmf_vars, "OVMF variables template")
            if os.path.samefile(ovmf_code, ovmf_vars_template):
                raise ValueError("OVMF CODE and VARS must be separate files")
        except (OSError, ValueError) as exc:
            print(f"qemu-boot-smoke: {exc}", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="wsm-qemu-smoke-") as temporary:
        work = Path(temporary).resolve()
        qcow2 = work / "disposable.qcow2"
        if args.firmware == "uefi":
            # CODE stays read-only; only a private copy of the distinct VARS
            # template is writable by the guest. Host NVRAM is never passed in.
            assert ovmf_vars_template is not None
            ovmf_vars = copy_ovmf_vars_template(
                ovmf_vars_template, work / "OVMF_VARS.fd"
            )
        command = build_qemu_command(
            qemu, iso, qcow2, args.memory_mib, args.cpus,
            firmware=args.firmware,
            ovmf_code=args.ovmf_code,
            ovmf_vars=ovmf_vars,
        )

        if args.dry_run:
            print(json.dumps({
                "mode": "dry-run",
                "iso": str(iso),
                "iso_sha256": sha256_of(iso),
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
                "efi_variable_store": False,
                "host_efi_variables_modified": False,
                "guest_uefi_vars_writable": args.firmware == "uefi",
                "guest_uefi_vars_source": (
                    "private-copy-of-vars-template" if args.firmware == "uefi" else None
                ),
                "guest_installer_execution": False,
                "tool_closure": not_checked_tool_closure(args.tool_closure_marker),
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
                second_marker=args.installer_marker,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"qemu-boot-smoke: cannot start or capture QEMU: {exc}", file=sys.stderr)
            return 3

        serial = captured.stdout_tail.decode("utf-8", errors="replace")
        qemu_error = captured.stderr_tail.decode("utf-8", errors="replace").strip() or None
        marker_seen = captured.marker_seen
        # Parsed from the whole retained serial tail, not from the shortened
        # presentation tail below: the report is a machine contract, and losing
        # it to a display limit would turn a real observation into a failure.
        tool_closure = tool_closure_evidence(serial, args.tool_closure_marker)
        result = {
            "mode": "qemu-boot-smoke",
            "iso": str(iso),
            "iso_sha256": sha256_of(iso),
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
            "efi_variable_store": False,
            "host_efi_variables_modified": False,
            "guest_uefi_vars_writable": args.firmware == "uefi",
            "guest_uefi_vars_source": (
                "private-copy-of-vars-template" if args.firmware == "uefi" else None
            ),
            # True only when the guest itself printed the installer marker.
            # Boot evidence alone must never be reported as installer evidence.
            "guest_installer_execution": captured.second_marker_seen,
            # The guest's own answer about the tools the installer will run.
            # "not-checked" when the caller did not ask; never a pass by default.
            "tool_closure": tool_closure,
        }
        print(json.dumps(result, sort_keys=True, indent=2))
        if not marker_seen:
            if not args.boot_marker:
                print("qemu-boot-smoke: boot not confirmed; provide --boot-marker from the guest serial console", file=sys.stderr)
            else:
                print("qemu-boot-smoke: configured boot marker was not observed", file=sys.stderr)
            return EXIT_BOOT_NOT_CONFIRMED
        if tool_closure["status"] == STATUS_FAIL:
            print(
                "qemu-boot-smoke: the booted guest did not prove the installer's tools "
                f"exist and are executable: {'; '.join(tool_closure['problems'])}",
                file=sys.stderr,
            )
            return EXIT_TOOL_CLOSURE_FAILED
        if not args.tool_closure_marker:
            print(
                "qemu-boot-smoke: NOTE boot alone does not prove the installer's tools "
                "exist in the image; pass --tool-closure-marker WSM_TOOL_CLOSURE to "
                "have the guest report them",
                file=sys.stderr,
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
