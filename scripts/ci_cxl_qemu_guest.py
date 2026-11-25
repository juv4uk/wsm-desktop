#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot a disposable QEMU CXL Type-3 guest and summarize its read-only sysfs topology."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import selectors
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qemu_boot_smoke import run_bounded_process

KERNEL_TIMEOUT_SECONDS = 90
MAX_MODULE_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_MODULE_TOTAL_BYTES = 96 * 1024 * 1024
MAX_INITRAMFS_BYTES = 256 * 1024 * 1024
MAX_SERIAL_BYTES = 64 * 1024
MAX_STDERR_BYTES = 32 * 1024
MAX_MODULE_COUNT = 128
GUEST_DONE_MARKER = "WSM_CXL_GUEST_DONE"
MODULE_REQUESTS = ("cxl_acpi", "cxl_pci", "cxl_mem", "cxl_port")


class CxlGuestError(RuntimeError):
    """The isolated CXL guest did not reach the expected evidence."""


SAFE_GUEST_STATUSES = {
    "type3-memdev-discovered",
    "cxl-sysfs-topology-incomplete",
}
SAFE_GUEST_STAGES = {
    "WSM_CXL_STAGE_INIT",
    "WSM_CXL_STAGE_MODULE_LOAD",
}
GUEST_COUNTS_PATTERN = re.compile(
    r"^WSM_CXL_COUNTS devices=([0-9]{1,5}) ports=([0-9]{1,5}) "
    r"memdevs=([0-9]{1,5}) edges=([0-9]{1,5})$"
)


def summarize_guest_serial(serial: str) -> str:
    """Return only allow-listed guest markers; never echo raw console output."""
    stages = [line for line in SAFE_GUEST_STAGES if line in serial.splitlines()]
    status = "unknown"
    counts = "not-reported"
    for line in serial.splitlines():
        if line.startswith("WSM_CXL_STATUS="):
            candidate = line.split("=", 1)[1]
            status = candidate if candidate in SAFE_GUEST_STATUSES else "unknown"
        match = GUEST_COUNTS_PATTERN.fullmatch(line)
        if match:
            labels = ("devices", "ports", "memdevs", "edges")
            counts = ",".join(
                f"{label}={int(value)}"
                for label, value in zip(labels, match.groups())
            )
    return f"stages={','.join(sorted(stages)) or 'none'};status={status};counts={counts}"


def parse_insmod_plan(text: str, module_root: Path) -> list[Path]:
    """Accept only resolved insmod paths contained in the current kernel module tree."""
    root = module_root.resolve(strict=True)
    ordered: list[Path] = []
    seen: set[Path] = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0] != "insmod":
            continue
        source = Path(fields[1]).resolve(strict=True)
        if root not in source.parents:
            raise CxlGuestError("module dependency escaped the selected kernel tree")
        if not source.name.endswith((".ko", ".ko.zst", ".ko.xz")):
            continue
        if source not in seen:
            ordered.append(source)
            seen.add(source)
    return ordered


def resolve_module_order(kernel_release: str, modprobe: str = "modprobe") -> list[Path]:
    """Read modprobe's dependency plan without loading or unloading host modules."""
    root = Path("/lib/modules") / kernel_release
    root.resolve(strict=True)
    ordered: list[Path] = []
    seen: set[Path] = set()
    for module in MODULE_REQUESTS:
        result = subprocess.run(
            [modprobe, "--show-depends", module],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise CxlGuestError(
                f"modprobe --show-depends {module} failed ({result.returncode}): "
                f"{result.stderr[-1200:]}"
            )
        for source in parse_insmod_plan(result.stdout, root):
            if source not in seen:
                ordered.append(source)
                seen.add(source)
    if not ordered:
        raise CxlGuestError("no loadable CXL modules were found")
    if len(ordered) > MAX_MODULE_COUNT:
        raise CxlGuestError(f"CXL dependency closure exceeds {MAX_MODULE_COUNT} modules")
    return ordered


def decompress_module(source: Path, total_remaining: int) -> bytes:
    """Decompress one module with a fixed memory ceiling and wall-clock timeout."""
    size = source.stat().st_size
    if size <= 0 or size > MAX_MODULE_ARCHIVE_BYTES:
        raise CxlGuestError(
            f"module archive size {size} is outside the allowed range: {source.name}"
        )
    if total_remaining <= 0:
        raise CxlGuestError("CXL module dependency closure exhausted its aggregate byte budget")

    if source.name.endswith(".ko.zst"):
        command = ["zstd", "-q", "-d", "-c", str(source)]
    elif source.name.endswith(".ko.xz"):
        command = ["xz", "-d", "-c", str(source)]
    elif source.name.endswith(".ko.gz"):
        command = ["gzip", "-d", "-c", str(source)]
    else:
        if size > total_remaining:
            raise CxlGuestError(f"uncompressed module exceeds remaining budget: {source.name}")
        payload = source.read_bytes()
        if not payload or len(payload) > total_remaining:
            raise CxlGuestError(f"uncompressed module exceeds remaining budget: {source.name}")
        return payload

    output_limit = min(MAX_MODULE_ARCHIVE_BYTES * 4, total_remaining)
    result = run_bounded_process(
        command,
        timeout_seconds=15,
        marker=None,
        max_stdout_bytes=output_limit,
        max_stderr_bytes=8 * 1024,
    )
    if result.timed_out:
        raise CxlGuestError(f"module decompression timed out: {source.name}")
    if result.stdout_truncated:
        raise CxlGuestError(f"decompressed module exceeded {output_limit} bytes: {source.name}")
    if result.returncode != 0:
        raise CxlGuestError(f"module decompression failed for {source.name}")
    payload = result.stdout_tail
    if not payload or len(payload) > total_remaining:
        raise CxlGuestError(f"decompressed module exceeds remaining budget: {source.name}")
    return payload


def run_bounded_file(
    command: list[str],
    *,
    cwd: Path,
    destination: Path,
    timeout_seconds: float,
    max_bytes: int,
) -> int:
    """Stream a child process to a new file with hard byte and time ceilings."""
    if timeout_seconds <= 0 or max_bytes < 1:
        raise ValueError("timeout_seconds and max_bytes must be positive")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
        close_fds=True,
        start_new_session=True,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise CxlGuestError("child process stdout pipe was not created")

    selector = selectors.DefaultSelector()
    total = 0
    created = False
    deadline = time.monotonic() + timeout_seconds
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        with destination.open("xb") as output:
            created = True
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CxlGuestError("initramfs pipeline exceeded its time limit")
                events = selector.select(min(0.1, remaining))
                for key, _ in events:
                    chunk = os.read(key.fd, 64 * 1024)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise CxlGuestError(
                            f"initramfs output exceeded the {max_bytes}-byte ceiling"
                        )
                    output.write(chunk)

            try:
                returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise CxlGuestError("initramfs pipeline exceeded its time limit") from exc
            if returncode != 0:
                raise CxlGuestError(f"initramfs pipeline failed with exit code {returncode}")
            if total <= 0:
                raise CxlGuestError("initramfs pipeline produced an empty archive")
            return total
    except BaseException:
        try:
            # Kill the whole process group: the shell pipeline may have left
            # children holding stdout open even if the shell itself exited.
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if created:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        selector.close()
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()


def create_busybox_root(guest_root: Path) -> None:
    busybox = shutil.which("busybox")
    if not busybox:
        raise CxlGuestError("static BusyBox is unavailable")
    applets = ("sh", "mount", "mkdir", "sleep", "poweroff", "insmod", "readlink")
    available = set(subprocess.run(
        [busybox, "--list"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.splitlines())
    missing = [name for name in applets if name not in available]
    if missing:
        raise CxlGuestError(f"BusyBox is missing required applets: {', '.join(missing)}")

    for directory in ("bin", "dev", "proc", "sys", "tmp", "lib/modules/cxl"):
        (guest_root / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(busybox, guest_root / "bin/busybox")
    for applet in applets:
        link = guest_root / "bin" / applet
        if not link.exists():
            link.symlink_to("busybox")
    for node, mode, major, minor in (
        ("console", "600", 5, 1),
        ("null", "666", 1, 3),
        ("zero", "666", 1, 5),
        ("ttyS0", "600", 4, 64),
    ):
        subprocess.run(
            ["sudo", "mknod", "-m", mode, str(guest_root / "dev" / node),
             "c", str(major), str(minor)],
            check=True,
            timeout=10,
        )


def install_guest_modules(guest_root: Path, kernel_release: str) -> list[str]:
    sources = resolve_module_order(kernel_release)
    guest_paths: list[str] = []
    total = 0
    for index, source in enumerate(sources):
        payload = decompress_module(source, MAX_MODULE_TOTAL_BYTES - total)
        total += len(payload)
        filename = source.name
        for suffix in (".ko.zst", ".ko.xz"):
            if filename.endswith(suffix):
                filename = filename[:-len(suffix)] + ".ko"
                break
        if not filename.endswith(".ko"):
            raise CxlGuestError(f"unexpected module filename: {source.name}")
        destination = guest_root / "lib/modules/cxl" / f"{index:02d}-{filename}"
        destination.write_bytes(payload)
        guest_paths.append("/lib/modules/cxl/" + destination.name)
    if total > MAX_MODULE_TOTAL_BYTES:
        raise CxlGuestError("CXL module payload exceeded aggregate size cap")
    return guest_paths


def write_guest_init(guest_root: Path, module_paths: list[str]) -> None:
    module_lines = "\n".join(
        f'insmod "{path}" || guest_fail "module-{index}"'
        for index, path in enumerate(module_paths)
    )
    init = f"""#!/bin/sh
set -eu

guest_fail() {{
    echo "WSM_CXL_GUEST_FAILURE:$1" > /dev/console
    sleep 2
    poweroff -f
    exit 1
}}

echo WSM_CXL_STAGE_INIT > /dev/console
mount -t proc -o ro,nosuid,nodev,noexec proc /proc || guest_fail proc-mount
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs /sys || guest_fail sysfs-mount
mount -t devtmpfs devtmpfs /dev || true
echo WSM_CXL_STAGE_MODULE_LOAD > /dev/console
{module_lines}
sleep 2

devices=0
ports=0
memdevs=0
edges=0
for entry in /sys/bus/cxl/devices/*; do
    [ -e "$entry" ] || continue
    name=${{entry##*/}}
    case "$name" in
        root*|host*|port*|mem*|decoder*|endpoint*)
            echo "WSM_CXL_DEVICE=$name"
            devices=$((devices + 1))
            case "$name" in
                root*|host*|port*) ports=$((ports + 1)) ;;
                mem*) memdevs=$((memdevs + 1)) ;;
            esac
            ;;
    esac
    for link in "$entry"/uport "$entry"/dport*; do
        [ -L "$link" ] || continue
        link_name=${{link##*/}}
        target=$(readlink "$link" 2>/dev/null || true)
        target=${{target##*/}}
        case "$target" in
            root*|host*|port*|mem*|decoder*|endpoint*)
                echo "WSM_CXL_EDGE=$name.$link_name->$target"
                edges=$((edges + 1))
                ;;
            *:*)
                echo "WSM_CXL_EDGE=$name.$link_name->pci-function"
                edges=$((edges + 1))
                ;;
        esac
    done
done

echo "WSM_CXL_COUNTS devices=$devices ports=$ports memdevs=$memdevs edges=$edges"
if [ "$memdevs" -gt 0 ] && [ "$ports" -gt 0 ]; then
    echo "WSM_CXL_STATUS=type3-memdev-discovered"
else
    echo "WSM_CXL_STATUS=cxl-sysfs-topology-incomplete"
    echo "WSM_CXL_SYSFS_INCOMPLETE=1"
    echo "WSM_CXL_FAILURE_DIAGNOSTICS=redacted"
fi
echo "{GUEST_DONE_MARKER}" > /dev/console
sleep 1
poweroff -f
"""
    target = guest_root / "init"
    target.write_text(init, encoding="utf-8")
    target.chmod(0o755)


def create_initramfs(guest_root: Path, destination: Path) -> None:
    command = [
        "bash",
        "-c",
        "set -euo pipefail; find . -print0 | sort -z | cpio --null --create --format=newc 2>/dev/null | gzip -9",
    ]
    run_bounded_file(
        command,
        cwd=guest_root,
        destination=destination,
        timeout_seconds=30,
        max_bytes=MAX_INITRAMFS_BYTES,
    )


def build_qemu_command(qemu: str, kernel: Path, initramfs: Path) -> list[str]:
    return [
        qemu,
        "-no-user-config",
        "-nodefaults",
        "-machine", "q35,cxl=on",
        "-accel", "tcg",
        "-m", "1G,maxmem=2G,slots=8",
        "-smp", "1",
        "-kernel", str(kernel),
        "-initrd", str(initramfs),
        "-append", "console=ttyS0,115200 rdinit=/init panic=-1 loglevel=4",
        "-object", "memory-backend-ram,id=vmem0,size=256M,share=on",
        "-device", "pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1",
        "-device", "cxl-rp,port=0,bus=cxl.1,id=root_port0,chassis=0,slot=0",
        "-device", "cxl-type3,bus=root_port0,volatile-memdev=vmem0,id=cxl-vmem0",
        "-machine", "cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-nic", "none",
        "-no-reboot",
    ]


def main() -> int:
    kernel_release = os.uname().release
    kernel = Path("/boot") / f"vmlinuz-{kernel_release}"
    qemu = shutil.which("qemu-system-x86_64")
    if not kernel.is_file():
        raise CxlGuestError(f"runner kernel image is unavailable: {kernel}")
    if not qemu:
        raise CxlGuestError("qemu-system-x86_64 is unavailable")
    if not all(shutil.which(name) for name in ("modprobe", "zstd", "cpio", "gzip")):
        raise CxlGuestError("modprobe, zstd, cpio, and gzip are required")

    with tempfile.TemporaryDirectory(prefix="wsm-cxl-guest-") as directory:
        work = Path(directory)
        guest_root = work / "rootfs"
        guest_root.mkdir()
        create_busybox_root(guest_root)
        module_paths = install_guest_modules(guest_root, kernel_release)
        write_guest_init(guest_root, module_paths)
        initramfs = work / "initramfs.cpio.gz"
        create_initramfs(guest_root, initramfs)

        if kernel.stat().st_size > 128 * 1024 * 1024:
            raise CxlGuestError("runner kernel image exceeds the 128 MiB input cap")
        kernel_copy = work / "vmlinuz"
        with subprocess.Popen(["sudo", "cat", str(kernel)], stdout=subprocess.PIPE) as process:
            if process.stdout is None:
                raise CxlGuestError("could not read runner kernel image")
            with kernel_copy.open("wb") as output:
                shutil.copyfileobj(process.stdout, output, length=1024 * 1024)
            if process.wait(timeout=10) != 0:
                raise CxlGuestError("could not stage runner kernel image")

        command = build_qemu_command(qemu, kernel_copy, initramfs)
        result = run_bounded_process(
            command,
            timeout_seconds=KERNEL_TIMEOUT_SECONDS,
            marker=GUEST_DONE_MARKER,
            max_stdout_bytes=MAX_SERIAL_BYTES,
            max_stderr_bytes=MAX_STDERR_BYTES,
        )
        serial = result.stdout_tail.decode("utf-8", errors="replace")
        safe_summary = summarize_guest_serial(serial)
        if result.timed_out:
            raise CxlGuestError(f"QEMU CXL guest timed out; {safe_summary}")
        if result.returncode != 0:
            raise CxlGuestError(f"QEMU CXL guest exited {result.returncode}; {safe_summary}")
        if result.stdout_truncated or result.stderr_truncated:
            raise CxlGuestError("QEMU CXL guest exceeded bounded serial/stderr capture limits")
        if not result.marker_seen:
            raise CxlGuestError(f"QEMU CXL guest did not print completion marker; {safe_summary}")

        summary_fields = dict(
            field.split("=", 1) for field in safe_summary.split(";") if "=" in field
        )
        status_value = summary_fields.get("status", "unknown")
        status = status_value if status_value in SAFE_GUEST_STATUSES else None
        counts_value = summary_fields.get("counts", "not-reported")
        counts = counts_value if counts_value != "not-reported" else None
        devices: list[str] = []
        edges: list[str] = []
        for line in serial.splitlines():
            if line.startswith("WSM_CXL_DEVICE="):
                devices.append(line.split("=", 1)[1])
            elif line.startswith("WSM_CXL_EDGE="):
                edges.append(line.split("=", 1)[1])

        # Emit only allow-listed synthetic names and report-local relationships.
        import re
        device_pattern = re.compile(r"^(?:root|host|port|mem|decoder|endpoint)[A-Za-z0-9._-]{0,40}$")
        edge_pattern = re.compile(r"^[A-Za-z0-9._-]{1,40}\.[A-Za-z0-9._-]{1,40}->(?:[A-Za-z0-9._-]{1,40}|pci-function)$")
        devices = sorted({name for name in devices if device_pattern.fullmatch(name)})
        edges = sorted({edge for edge in edges if edge_pattern.fullmatch(edge)})
        print(json.dumps({
            "qemu_guest_status": status,
            "synthetic_devices": devices,
            "synthetic_edges": edges,
            "counts": counts,
            "kernel_release": kernel_release,
            "qemu_acceleration": "tcg",
            "host_disk_attached": False,
            "network_attached": False,
            "host_device_passthrough": False,
            "host_modules_loaded_or_unloaded": False,
            "host_sysfs_written": False,
            "serial_bytes_seen": result.stdout_bytes_seen,
            "stderr_bytes_seen": result.stderr_bytes_seen,
            "serial_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
        }, indent=2, sort_keys=True))

        if status != "type3-memdev-discovered":
            raise CxlGuestError(
                "Linux guest did not expose a Type-3 memdev and CXL port in sysfs; "
                safe_summary
            )
        if not devices or not any(name.startswith("mem") for name in devices):
            raise CxlGuestError("CXL guest reported Type-3 status without a memdev entry")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CxlGuestError as exc:
        print(f"qemu-cxl-guest: {exc}", file=sys.stderr)
        raise SystemExit(1)