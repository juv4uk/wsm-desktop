#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the real wsm-hwcheck collector inside a disposable QEMU Linux guest.

The host downloads one immutable, digest-pinned CPython archive, assembles a
small initramfs, and starts QEMU TCG without a disk, NIC, host-device passthrough,
shared folder, or EFI variable store. The guest mounts procfs/sysfs read-only,
runs this repository's wsm_hwcheck package, and returns one JSON report over
the bounded serial pipe. The host validates the report against schema v1.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qemu_boot_smoke import run_bounded_process

SCHEMA_PATH = ROOT / "schemas" / "hardware-report.schema.json"

PYTHON_VERSION = "3.11.18"
PYTHON_RELEASE = "20261123"
PYTHON_ARCHIVE = (
    "cpython-3.11.18+20261123-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
)
PYTHON_SHA256 = "75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316"
PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_RELEASE}/{PYTHON_ARCHIVE.replace('+', '%2B')}"
)
MAX_PYTHON_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_INITRAMFS_BYTES = 256 * 1024 * 1024
MAX_SERIAL_TAIL_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 512 * 1024
MAX_STDERR_TAIL_BYTES = 256 * 1024
PIPE_CHUNK_BYTES = 64 * 1024
QEMU_TIMEOUT_SECONDS = 150
POST_KILL_DRAIN_SECONDS = 2.0

REPORT_BEGIN = b"WSM_HWCHECK_REPORT_BEGIN\n"
REPORT_END = b"\nWSM_HWCHECK_REPORT_END"
FORBIDDEN_REPORT_KEYS = {
    "serial",
    "serial_number",
    "mac",
    "mac_address",
    "uuid",
    "hostname",
    "username",
    "ip_address",
    "wwn",
}


class GuestRunError(RuntimeError):
    """A bounded QEMU guest run or report validation failed."""


def log(message: str) -> None:
    print(f"QEMU wsm-hwcheck guest: {message}", flush=True)


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise GuestRunError(f"required host command is missing: {name}")
    return resolved


def download_pinned_python(destination: Path) -> Path:
    """Download the immutable upstream archive and verify its exact SHA-256."""
    request = urllib.request.Request(
        PYTHON_URL,
        headers={"User-Agent": "wsm-desktop-qemu-hwcheck-ci/1"},
    )
    digest = hashlib.sha256()
    total = 0

    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            status = getattr(response, "status", 200)
            if status != 200:
                raise GuestRunError(f"Python archive download returned HTTP {status}")

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PYTHON_ARCHIVE_BYTES:
                    raise GuestRunError("Python archive exceeded the 40 MiB download limit")
                digest.update(chunk)
                output.write(chunk)
    except GuestRunError:
        raise
    except Exception as exc:
        raise GuestRunError(f"could not download pinned Python runtime: {exc}") from exc

    actual = digest.hexdigest()
    if actual != PYTHON_SHA256:
        raise GuestRunError(
            f"Python archive SHA-256 mismatch: expected {PYTHON_SHA256}, got {actual}"
        )
    if total == 0:
        raise GuestRunError("Python archive download was empty")

    log(
        f"verified CPython {PYTHON_VERSION} archive "
        f"({total:,} bytes, SHA-256 {actual[:16]}…)"
    )
    return destination


def extract_python_archive(archive_path: Path, destination: Path) -> Path:
    """Extract using Python's safe data filter and locate python/install."""
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 50_000:
                raise GuestRunError("Python archive contains too many entries")
            expanded_bytes = sum(max(member.size, 0) for member in members)
            if expanded_bytes > MAX_INITRAMFS_BYTES:
                raise GuestRunError("Python archive expands beyond the 256 MiB limit")
            archive.extractall(destination, filter="data")
    except GuestRunError:
        raise
    except Exception as exc:
        raise GuestRunError(f"could not safely extract Python archive: {exc}") from exc

    # Install-only archives rewrite python/install/* to python/* at release time.
    install_root = destination / "python"
    python_binary = install_root / "bin" / f"python{PYTHON_VERSION.rsplit('.', 1)[0]}"
    if not python_binary.is_file():
        raise GuestRunError(
            f"pinned archive does not contain the expected interpreter: {python_binary}"
        )
    return install_root


def parse_ldd_paths(output: str) -> set[Path]:
    """Extract resolved absolute library paths from ldd output."""
    result: set[Path] = set()
    if "not found" in output:
        missing = [
            line.strip()
            for line in output.splitlines()
            if "not found" in line
        ]
        raise GuestRunError("unresolved Python runtime dependency: " + "; ".join(missing))

    for line in output.splitlines():
        match = re.search(r"=>\s+(/[^ \t]+)", line)
        if match:
            result.add(Path(match.group(1)))
            continue
        direct = re.match(r"^\s*(/[^ \t]+)\s+\(", line)
        if direct:
            result.add(Path(direct.group(1)))

    return result


def copy_external_elf_dependencies(install_root: Path, guest_root: Path) -> set[str]:
    """Copy only resolved system ELF dependencies, preserving absolute paths.

    The standalone Python tree is copied separately. ldd is run only against
    binaries from the digest-pinned upstream archive. Any unresolved dependency
    fails the job rather than being silently omitted.
    """
    ldd = require_command("ldd")
    candidates = [install_root / "bin" / f"python{PYTHON_VERSION.rsplit('.', 1)[0]}"]
    candidates.extend(
        path
        for path in install_root.rglob("*.so*")
        if path.is_file()
    )

    copied: set[str] = set()
    library_directories: set[str] = set()

    for binary in sorted(set(candidates)):
        completed = subprocess.run(
            [ldd, str(binary)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        if "not a dynamic executable" in output or "statically linked" in output:
            continue
        if completed.returncode not in (0, 1):
            raise GuestRunError(
                f"ldd failed for {binary.relative_to(install_root)}: {output[-1000:]}"
            )

        for dependency in parse_ldd_paths(output):
            try:
                resolved = dependency.resolve(strict=True)
            except OSError as exc:
                raise GuestRunError(f"ELF dependency is absent: {dependency}: {exc}") from exc

            try:
                relative = resolved.relative_to(install_root.resolve())
                # This dependency is already inside the Python installation copied to /opt/python.
                library_directories.add(str(Path("/opt/python") / relative.parent))
                continue
            except ValueError:
                pass

            destination = guest_root / dependency.relative_to("/")
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved, destination, follow_symlinks=True)
            copied.add(str(dependency))
            library_directories.add(str(dependency.parent))

    if not copied:
        raise GuestRunError("no external glibc dependencies were discovered; refusing an unverified runtime")
    log(f"copied {len(copied)} external ELF dependency paths into the guest rootfs")
    return library_directories


def copy_python_and_collector(install_root: Path, guest_root: Path) -> set[str]:
    python_target = guest_root / "opt" / "python"
    python_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(install_root, python_target, symlinks=True)

    package_target = guest_root / "opt" / "wsm" / "wsm_hwcheck"
    package_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "wsm_hwcheck", package_target)

    return copy_external_elf_dependencies(
        install_root,
        guest_root,
    )


def create_busybox_root(guest_root: Path) -> None:
    busybox = shutil.which("busybox")
    if not busybox:
        raise GuestRunError("busybox-static is missing from the runner")

    bin_dir = guest_root / "bin"
    for directory in (
        bin_dir,
        guest_root / "dev",
        guest_root / "proc",
        guest_root / "sys",
        guest_root / "tmp",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(busybox, bin_dir / "busybox")
    for applet in ("sh", "mount", "mkdir", "cat", "ls", "sleep", "sync", "poweroff"):
        link = bin_dir / applet
        if not link.exists():
            link.symlink_to("busybox")

    subprocess.run(
        ["sudo", "mknod", "-m", "666", str(guest_root / "dev" / "null"), "c", "1", "3"],
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["sudo", "mknod", "-m", "666", str(guest_root / "dev" / "zero"), "c", "1", "5"],
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["sudo", "mknod", "-m", "600", str(guest_root / "dev" / "console"), "c", "5", "1"],
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["sudo", "mknod", "-m", "666", str(guest_root / "dev" / "ttyS0"), "c", "4", "64"],
        check=True,
        timeout=10,
    )


def write_guest_init(guest_root: Path, library_directories: set[str]) -> None:
    ld_path = ":".join(sorted(library_directories))
    init = f"""#!/bin/sh
set -eu
export PATH=/bin:/opt/python/bin
export PYTHONHOME=/opt/python
export PYTHONPATH=/opt/wsm
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH={ld_path}

echo "WSM_HWCHECK_GUEST_INIT_STARTED" > /dev/console
for command in sh mount mkdir cat ls sleep sync poweroff python3.11; do
    command -v "$command" > /dev/console 2>&1 || {{
        echo "WSM_HWCHECK_GUEST_ERROR=missing-command-$command" > /dev/console
        poweroff -f
        exit 1
    }}
done
if ! mount -t proc -o ro proc /proc; then
    echo "WSM_HWCHECK_GUEST_ERROR=proc-mount"
    poweroff -f
    exit 1
fi
if ! mount -t sysfs -o ro sysfs /sys; then
    echo "WSM_HWCHECK_GUEST_ERROR=sysfs-mount"
    poweroff -f
    exit 1
fi
mount -t devtmpfs devtmpfs /dev || true
mkdir -p /tmp
echo "WSM_HWCHECK_GUEST_MOUNTS_READY"

echo "WSM_HWCHECK_GUEST_PYTHON_START"
python3.11 --version
python3.11 -S -c 'import json, selectors, subprocess, pathlib, gzip, base64' || {{
    echo "WSM_HWCHECK_GUEST_ERROR=python-import"
    poweroff -f
    exit 1
}}
echo "WSM_HWCHECK_GUEST_COLLECTOR_START"
if python3.11 -S -m wsm_hwcheck --compact --output /tmp/hardware-report.json; then
    status=0
else
    status=$?
fi
if [ "$status" -ne 0 ]; then
    echo "WSM_HWCHECK_GUEST_ERROR=collector-$status"
    poweroff -f
    exit 1
fi
if [ ! -s /tmp/hardware-report.json ]; then
    echo "WSM_HWCHECK_GUEST_ERROR=empty-report"
    poweroff -f
    exit 1
fi
echo "WSM_HWCHECK_GUEST_REPORT_READY"

echo "WSM_HWCHECK_REPORT_BEGIN"
cat /tmp/hardware-report.json
echo
echo "WSM_HWCHECK_REPORT_END"
echo "WSM_HWCHECK_GUEST_POWERING_OFF"
sync
poweroff -f
"""
    init_path = guest_root / "init"
    init_path.write_text(init, encoding="utf-8")
    init_path.chmod(0o755)


def create_initramfs(guest_root: Path, output_path: Path) -> None:
    command = [
        "bash",
        "-euo",
        "pipefail",
        "-c",
        "find . -print0 | sort -z | cpio --null --create --format=newc | gzip -9",
    ]
    with output_path.open("wb") as output:
        completed = subprocess.run(
            command,
            cwd=guest_root,
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
    if completed.returncode != 0:
        raise GuestRunError(
            "could not create initramfs: "
            + completed.stderr.decode("utf-8", errors="replace")[-2000:]
        )
    if output_path.stat().st_size == 0 or output_path.stat().st_size > MAX_INITRAMFS_BYTES:
        raise GuestRunError("initramfs is empty or exceeds the 256 MiB ceiling")


def select_runner_kernel() -> Path:
    candidates = [
        path
        for path in Path("/boot").glob("vmlinuz-*")
        if path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        raise GuestRunError("no runner Linux kernel found under /boot")

    def version_key(path: Path) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", path.name))

    return max(candidates, key=version_key)


def extract_report(serial: bytes) -> dict[str, Any]:
    # The guest serial TTY may translate LF to CRLF; normalize before marker parsing.
    normalized = serial.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    begin_marker = b"WSM_HWCHECK_REPORT_BEGIN"
    end_marker = b"WSM_HWCHECK_REPORT_END"
    start = normalized.rfind(begin_marker)
    if start < 0:
        raise GuestRunError("guest report begin marker was not observed")
    payload_start = normalized.find(b"\n", start)
    if payload_start < 0:
        end_hint = normalized.find(end_marker, start + len(begin_marker))
        around = normalized[start : start + 256]
        tail = normalized[-512:]
        raise GuestRunError(
            "guest report begin marker had no line terminator; "
            f"offset={start}, end_marker_offset={end_hint}, "
            f"bytes_after_begin={len(normalized) - start - len(begin_marker)}, "
            f"around={around!r}, tail={tail!r}"
        )
    payload_start += 1
    end = normalized.find(end_marker, payload_start)
    if end < 0:
        raise GuestRunError("guest report end marker was not observed")
    payload = normalized[payload_start:end].strip()
    if len(payload) > MAX_REPORT_BYTES:
        raise GuestRunError(
            f"guest report exceeds the {MAX_REPORT_BYTES}-byte payload ceiling"
        )
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuestRunError(
            "guest report is not valid UTF-8; "
            f"bytes={len(payload)}, invalid_offset={exc.start}, "
            f"first64={payload[:64]!r}, last64={payload[-64:]!r}"
        ) from exc
    try:
        report = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise GuestRunError(
            "guest report payload is not clean JSON; "
            f"bytes={len(payload)}, line={exc.lineno}, column={exc.colno}, "
            f"offset={exc.pos}, first64={payload[:64]!r}, last64={payload[-64:]!r}"
        ) from exc
    if not isinstance(report, dict):
        raise GuestRunError("guest report root must be a JSON object")
    return report


def validate_guest_report(report: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise GuestRunError("host jsonschema dependency is missing") from exc

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(report),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise GuestRunError(f"guest report schema violation at {location}: {first.message}")

    if report.get("schema_version") != "1.0.0":
        raise GuestRunError("guest returned an unexpected hardware report schema version")
    privacy = report.get("privacy", {})
    if privacy.get("network_requests_performed") is not False:
        raise GuestRunError("guest report does not prove that network requests were absent")
    if privacy.get("network_upload_performed") is not False:
        raise GuestRunError("guest report does not prove that network upload was absent")
    if privacy.get("sensitive_identifiers_included") is not False:
        raise GuestRunError("guest report does not prove sensitive identifier redaction")

    def scan(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                    raise GuestRunError(f"guest report contains a forbidden identifier field: {key}")
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(report)
    categories = {
        device.get("category")
        for device in report.get("devices", [])
        if isinstance(device, dict)
    }
    if "cpu" not in categories:
        raise GuestRunError("guest report did not inventory the virtual CPU")


def build_and_run_guest(work_dir: Path) -> dict[str, Any]:
    qemu = require_command("qemu-system-x86_64")
    require_command("cpio")
    require_command("gzip")
    require_command("ldd")
    require_command("sudo")

    archive_path = work_dir / PYTHON_ARCHIVE
    download_pinned_python(archive_path)
    extracted = work_dir / "python-dist"
    install_root = extract_python_archive(archive_path, extracted)

    guest_root = work_dir / "rootfs"
    guest_root.mkdir()
    create_busybox_root(guest_root)
    library_directories = copy_python_and_collector(install_root, guest_root)
    write_guest_init(guest_root, library_directories)

    initrd = work_dir / "wsm-hwcheck-initramfs.cpio.gz"
    create_initramfs(guest_root, initrd)

    kernel_source = select_runner_kernel()
    guest_kernel = work_dir / "guest-kernel"
    subprocess.run(
        ["sudo", "cp", str(kernel_source), str(guest_kernel)],
        check=True,
        timeout=20,
    )
    subprocess.run(["sudo", "chmod", "0644", str(guest_kernel)], check=True, timeout=10)

    command = [
        qemu,
        "-machine", "q35,accel=tcg",
        "-cpu", "max",
        "-m", "1024",
        "-smp", "1",
        "-kernel", str(guest_kernel),
        "-initrd", str(initrd),
        "-append", "console=ttyS0,115200 rdinit=/init panic=-1",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-nic", "none",
        "-no-reboot",
    ]
    log("starting guest with TCG, no disk, no NIC, no host-device passthrough")
    result = run_bounded_process(
        command,
        timeout_seconds=QEMU_TIMEOUT_SECONDS,
        marker=REPORT_END.decode("ascii"),
    )
    serial = result.stdout_tail
    stderr = result.stderr_tail
    serial_text = serial.decode("utf-8", errors="replace")[-6000:]
    stderr_text = stderr.decode("utf-8", errors="replace")[-3000:]

    if result.timed_out:
        raise GuestRunError(
            f"QEMU guest exceeded the {QEMU_TIMEOUT_SECONDS}-second wall-clock limit; "
            f"bounded serial tail:\\n{serial_text}\\nbounded stderr tail:\\n{stderr_text}"
        )
    if result.returncode != 0:
        raise GuestRunError(
            f"QEMU exited with status {result.returncode}; "
            f"bounded serial tail:\\n{serial_text}\\nbounded stderr tail:\\n{stderr_text}"
        )
    if result.stdout_truncated:
        raise GuestRunError(
            "serial output exceeded the shared 1 MiB capture ceiling; "
            f"bounded serial tail:\\n{serial_text}"
        )
    if result.stderr_truncated:
        log("QEMU stderr exceeded its shared 256 KiB tail cap; discarded older diagnostics")
    if not result.marker_seen:
        raise GuestRunError(
            f"guest did not emit {REPORT_END.decode('ascii')}; "
            f"bounded serial tail:\\n{serial_text}\\nbounded stderr tail:\\n{stderr_text}"
        )

    report = extract_report(serial)
    validate_guest_report(report)
    return report


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="wsm-hwcheck-qemu-") as temporary:
            report = build_and_run_guest(Path(temporary))
        devices = report.get("devices", [])
        log(
            "PASS — actual wsm-hwcheck ran in the Linux guest; "
            f"schema={report['schema_version']}, devices={len(devices)}, "
            f"collectors={len(report.get('collectors', []))}"
        )
        log("the guest report passed schema v1.0.0 and strict-local privacy assertions")
        log("this is virtual guest runtime evidence, not physical hardware compatibility")
        return 0
    except Exception as exc:
        print(f"QEMU wsm-hwcheck guest: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
