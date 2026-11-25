#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the actual WSM hardware collector inside a disposable no-disk QEMU guest."""

from __future__ import annotations

import base64
from io import BytesIO
import gzip
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
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator, FormatChecker
from scripts.qemu_boot_smoke import run_bounded_process

PYTHON_TAG = "20261123"
PYTHON_ASSET = "cpython-3.11.18+20261123-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_TAG}/{PYTHON_ASSET.replace('+', '%2B')}"
)
PYTHON_SHA256 = "75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316"
REPORT_BEGIN = "WSM_HWCHECK_REPORT_BEGIN"
REPORT_END = "WSM_HWCHECK_REPORT_END"
REPORT_PREFIX = "WSM_HWCHECK_REPORT_Z64:"
MAX_PYTHON_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_TAR_MEMBERS = 50_000
MAX_TAR_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_INITRAMFS_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 512 * 1024
BUSYBOX_APPLETS = ("sh", "mount", "mkdir", "poweroff", "sleep", "sync")
QEMU_TIMEOUT_SECONDS = 90
GUEST_MEMORY_MIB = 2048

GUEST_INIT = """#!/bin/sh
set -eu

guest_fail() {{
    echo "WSM_HWCHECK_GUEST_FAILURE:$1" > /dev/console
    sleep 2
    poweroff -f
}}

echo WSM_HWCHECK_STAGE_INIT > /dev/console
mount -t proc -o ro,nosuid,nodev,noexec proc /proc || guest_fail "proc-mount"
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs /sys || guest_fail "sysfs-mount"
mkdir -p /tmp

export PATH=/opt/python/bin:/bin
export PYTHONHOME=/opt/python
export PYTHONPATH=/opt/wsm
export LD_LIBRARY_PATH={ld_library_path}

PYTHON=/opt/python/bin/python3.11
echo WSM_HWCHECK_STAGE_PYTHON_IMPORT > /dev/console
if ! "$PYTHON" -S -c 'import json, selectors, subprocess, pathlib, gzip, base64' > /dev/console 2>&1; then
    guest_fail "python-import-smoke"
fi
echo WSM_HWCHECK_STAGE_COLLECTOR_START > /dev/console
if ! "$PYTHON" -S -m wsm_hwcheck --compact --output /tmp/hardware-report.json > /dev/console 2>&1; then
    guest_fail "wsm-hwcheck-execution"
fi
if [ ! -s /tmp/hardware-report.json ]; then
    guest_fail "report-file-empty"
fi
echo WSM_HWCHECK_STAGE_COLLECTOR_DONE > /dev/console

echo {report_begin} > /dev/console
if ! "$PYTHON" -S - <<'PYREPORT' > /dev/console 2>&1
import base64
import gzip
from pathlib import Path

report_path = Path("/tmp/hardware-report.json")
if report_path.stat().st_size > {max_report_bytes}:
    raise SystemExit("guest report exceeds the 512 KiB report ceiling")
raw = report_path.read_bytes()
encoded = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
print("{report_prefix}" + encoded)
PYREPORT
then
    guest_fail "report-encoding"
fi
echo {report_end} > /dev/console

sync
poweroff -f
sleep 2
guest_fail "poweroff-returned"
"""


def _download_pinned_python(destination: Path) -> None:
    request = urllib.request.Request(
        PYTHON_URL,
        headers={"User-Agent": "wsm-hwcheck-qemu-ci/1.0"},
    )
    digest = hashlib.sha256()
    total_bytes = 0
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as out:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"pinned CPython download returned HTTP {status}")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PYTHON_ARCHIVE_BYTES:
            raise RuntimeError("pinned CPython archive exceeds the 40 MiB download ceiling")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_PYTHON_ARCHIVE_BYTES:
                raise RuntimeError("pinned CPython archive exceeds the 40 MiB download ceiling")
            digest.update(chunk)
            out.write(chunk)
    actual = digest.hexdigest()
    if actual != PYTHON_SHA256:
        raise RuntimeError(
            f"pinned CPython archive digest mismatch: expected {PYTHON_SHA256}, got {actual}"
        )


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > MAX_TAR_MEMBERS:
            raise RuntimeError("pinned CPython archive contains too many entries")
        expanded_bytes = sum(max(member.size, 0) for member in members)
        if expanded_bytes > MAX_TAR_EXPANDED_BYTES:
            raise RuntimeError("pinned CPython archive expands beyond the 256 MiB ceiling")
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe path in pinned Python archive: {member.name}")
        tar.extractall(destination, members=members, filter="data")


def _find_python_home(extract_root: Path) -> Path:
    matches = sorted(
        path for path in extract_root.rglob("python3.11")
        if path.is_file() and path.parent.name == "bin"
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one CPython 3.11 binary in the pinned archive, found {len(matches)}"
        )
    return matches[0].parent.parent.resolve()


def _elf_files(root: Path):
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            with candidate.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    yield candidate
        except OSError:
            continue


def _parse_ldd_paths(output: str) -> tuple[set[Path], list[str]]:
    libraries: set[Path] = set()
    missing: list[str] = []
    for line in output.splitlines():
        if "not found" in line:
            missing.append(line.strip())
            continue
        raw_path = None
        if "=>" in line:
            rhs = line.split("=>", 1)[1].strip()
            if rhs.startswith("/"):
                raw_path = rhs.split(" (", 1)[0].strip()
        else:
            candidate = line.strip().split(" (", 1)[0].strip()
            if candidate.startswith("/"):
                raw_path = candidate
        if raw_path:
            libraries.add(Path(raw_path))
    return libraries, missing


def _install_busybox_applets(bin_dir: Path) -> None:
    """Create every BusyBox applet link required by the guest init script."""
    for applet in BUSYBOX_APPLETS:
        link = bin_dir / applet
        if link.exists() or link.is_symlink():
            raise RuntimeError(f"BusyBox applet path already exists: {link}")
        link.symlink_to("busybox")


def render_guest_init(library_path: str) -> str:
    """Render the complete init script before any QEMU process is started."""
    return GUEST_INIT.format(
        ld_library_path=library_path,
        report_begin=REPORT_BEGIN,
        report_prefix=REPORT_PREFIX,
        report_end=REPORT_END,
        max_report_bytes=MAX_REPORT_BYTES,
    )


def _copy_runtime_dependencies(python_home: Path, rootfs: Path) -> list[Path]:
    """Copy only external shared libraries reported by ldd for the pinned runtime."""
    home_resolved = python_home.resolve()
    dependencies: set[Path] = set()
    elf_count = 0
    for binary in _elf_files(python_home):
        elf_count += 1
        completed = subprocess.run(
            ["ldd", str(binary)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        output = completed.stdout + completed.stderr
        if "not a dynamic executable" in output or "statically linked" in output:
            continue
        if completed.returncode not in (0, 1):
            raise RuntimeError(f"ldd failed for pinned runtime object {binary}: {output[-1200:]}")
        found, missing = _parse_ldd_paths(output)
        if missing:
            raise RuntimeError(
                f"unresolved shared libraries for {binary}: {'; '.join(missing)}"
            )
        for library in found:
            try:
                resolved = library.resolve(strict=True)
            except OSError as exc:
                raise RuntimeError(f"ldd reported a missing library path {library}") from exc
            if resolved == home_resolved or home_resolved in resolved.parents:
                continue
            dependencies.add(library)

    if elf_count == 0:
        raise RuntimeError("no ELF files found in pinned CPython installation")

    copied: list[Path] = []
    for source in sorted(dependencies, key=lambda item: str(item)):
        if not source.is_file():
            raise RuntimeError(f"required shared library is not a regular file: {source}")
        destination = rootfs / str(source).lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=True)
        copied.append(source)
    return copied


def _build_initramfs(work: Path) -> tuple[Path, int]:
    rootfs = work / "rootfs"
    for name in ("bin", "dev", "proc", "sys", "tmp", "opt"):
        (rootfs / name).mkdir(parents=True, exist_ok=True)

    archive = work / PYTHON_ASSET
    _download_pinned_python(archive)
    extract_root = work / "python-extract"
    extract_root.mkdir()
    _safe_extract_tar(archive, extract_root)
    python_home = _find_python_home(extract_root)

    copied_python = rootfs / "opt" / "python"
    shutil.copytree(python_home, copied_python, symlinks=True)
    libraries = _copy_runtime_dependencies(python_home, rootfs)
    library_dirs = sorted({str(path.parent) for path in libraries})
    library_path = os.pathsep.join(["/opt/python/lib", *library_dirs])

    runtime_env = os.environ.copy()
    runtime_env.update({
        "PYTHONHOME": str(python_home),
        "LD_LIBRARY_PATH": os.pathsep.join([str(python_home / "lib"), *library_dirs]),
    })
    _run = subprocess.run(
        [
            str(python_home / "bin" / "python3.11"),
            "-S",
            "-c",
            "import json, selectors, subprocess, pathlib, gzip, base64",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        env=runtime_env,
    )

    busybox = shutil.which("busybox")
    if not busybox:
        raise RuntimeError("busybox-static is required on the CI host")
    shutil.copy2(busybox, rootfs / "bin" / "busybox")
    _install_busybox_applets(rootfs / "bin")

    device_nodes = (
        ("console", 5, 1, 0o600),
        ("null", 1, 3, 0o666),
        ("zero", 1, 5, 0o666),
        ("urandom", 1, 9, 0o666),
        ("ttyS0", 4, 64, 0o600),
    )
    for name, major, minor, mode in device_nodes:
        node = rootfs / "dev" / name
        subprocess.run(
            ["sudo", "mknod", "-m", oct(mode)[2:], str(node), "c", str(major), str(minor)],
            check=True,
            capture_output=True,
            text=True,
        )

    shutil.copytree(ROOT / "wsm_hwcheck", rootfs / "opt" / "wsm" / "wsm_hwcheck")
    init_script = render_guest_init(library_path)
    init_path = rootfs / "init"
    init_path.write_text(init_script, encoding="utf-8")
    init_path.chmod(0o755)

    rootfs_bytes = sum(
        item.stat().st_size
        for item in rootfs.rglob("*")
        if item.is_file() and not item.is_symlink()
    )
    if rootfs_bytes > MAX_INITRAMFS_BYTES:
        raise RuntimeError("guest rootfs exceeds the 256 MiB initramfs size ceiling")

    initramfs = work / "initramfs.cpio.gz"
    with initramfs.open("wb") as output:
        subprocess.run(
            [
                "bash", "-o", "pipefail", "-c",
                "find . -print0 | sort -z | cpio --null --create --format=newc | gzip -n -9",
            ],
            cwd=rootfs,
            check=True,
            stdout=output,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    if not initramfs.is_file() or initramfs.stat().st_size == 0:
        raise RuntimeError("failed to create guest initramfs")
    if initramfs.stat().st_size > MAX_INITRAMFS_BYTES:
        raise RuntimeError("guest initramfs exceeds the 256 MiB ceiling")
    return initramfs, len(libraries)


def _find_runner_kernel() -> Path:
    candidates = sorted(Path("/boot").glob("vmlinuz-*"))
    if not candidates:
        raise RuntimeError("GitHub runner has no /boot/vmlinuz-* kernel image")
    return candidates[-1]


def _decode_guest_report(serial: str) -> dict:
    """Decode one CRLF-tolerant gzip/base64 report with a strict expansion bound."""
    serial = serial.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))
    if REPORT_BEGIN not in serial or REPORT_END not in serial:
        raise RuntimeError("guest report boundary markers were not fully captured")
    # Match the prefix anywhere in a line: TTY/UART implementations may
    # prepend control characters. Only the base64 payload is retained.
    matches = re.findall(
        rf"{re.escape(REPORT_PREFIX)}([A-Za-z0-9+/=]+)",
        serial,
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one compressed guest report, found {len(matches)}")
    if len(matches[0]) > 800_000:
        raise RuntimeError("compressed guest report exceeds the serial payload ceiling")
    try:
        compressed = base64.b64decode(matches[0], validate=True)
        with gzip.GzipFile(fileobj=BytesIO(compressed), mode="rb") as stream:
            payload = stream.read(MAX_REPORT_BYTES + 1)
            if len(payload) > MAX_REPORT_BYTES or stream.read(1):
                raise RuntimeError("decompressed guest report exceeds the 512 KiB ceiling")
        return json.loads(payload.decode("utf-8"))
    except (ValueError, OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot decode guest hardware report: {exc}") from exc


def _validate_report(report: dict) -> tuple[int, int]:
    schema_path = ROOT / "schemas" / "hardware-report.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(report),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = "; ".join(
            f"{list(error.absolute_path)}: {error.message}"
            for error in errors[:8]
        )
        raise RuntimeError(f"guest report failed Hardware Evidence Report v1.0.0: {rendered}")

    if report.get("schema_version") != "1.0.0":
        raise RuntimeError("guest report did not preserve schema v1.0.0")
    privacy = report.get("privacy", {})
    if privacy.get("network_requests_performed") is not False:
        raise RuntimeError("guest report network_requests_performed is not false")
    if privacy.get("network_upload_performed") is not False:
        raise RuntimeError("guest report network_upload_performed is not false")
    if privacy.get("sensitive_identifiers_included") is not False:
        raise RuntimeError("guest report sensitive_identifiers_included is not false")

    forbidden_keys = {
        "serial", "serial_number", "mac", "mac_address", "uuid",
        "hostname", "username", "ip_address", "wwn",
    }

    def reject_sensitive_fields(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).casefold() in forbidden_keys:
                    raise RuntimeError(f"guest report contains forbidden identifier key: {key}")
                reject_sensitive_fields(child)
        elif isinstance(value, list):
            for child in value:
                reject_sensitive_fields(child)

    reject_sensitive_fields(report)

    devices = report.get("devices", [])
    functional_tests = [
        test for device in devices
        for test in device.get("functional_tests", [])
    ]
    if any(test.get("status") == "passed" for test in functional_tests):
        raise RuntimeError(
            "inventory-only guest unexpectedly reported a passed functional test"
        )
    categories = {
        device.get("category")
        for device in devices
        if isinstance(device, dict)
    }
    if "cpu" not in categories:
        raise RuntimeError("guest report did not inventory the virtual CPU")
    return len(devices), len(functional_tests)


def main() -> int:
    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        raise RuntimeError("qemu-system-x86_64 is required on the CI host")
    for tool in ("ldd", "cpio", "gzip", "sudo", "mknod"):
        if not shutil.which(tool):
            raise RuntimeError(f"required CI tool is unavailable: {tool}")

    with tempfile.TemporaryDirectory(prefix="wsm-hwcheck-qemu-guest-") as directory:
        work = Path(directory)
        initramfs, dependency_count = _build_initramfs(work)
        kernel_copy = work / "guest-kernel"
        # Runner kernels in /boot are root-readable; copy them read-only into
        # the disposable workspace without changing the source or host boot state.
        with kernel_copy.open("wb") as kernel_output:
            subprocess.run(
                ["sudo", "cat", str(_find_runner_kernel())],
                check=True,
                stdout=kernel_output,
                timeout=30,
            )
        kernel_copy.chmod(0o644)

        command = [
            qemu,
            "-machine", "q35,accel=tcg",
            "-cpu", "max",
            "-m", str(GUEST_MEMORY_MIB),
            "-smp", "1",
            "-nodefaults",
            "-kernel", str(kernel_copy),
            "-initrd", str(initramfs),
            "-append", "console=ttyS0,115200 rdinit=/init panic=-1 loglevel=3",
            "-display", "none",
            "-serial", "stdio",
            "-monitor", "none",
            "-nic", "none",
            "-no-reboot",
        ]
        forbidden = {
            "-drive", "-blockdev", "-cdrom", "-fsdev", "-virtfs",
            "-device", "-bios", "-pflash",
        }
        if any(argument in forbidden for argument in command):
            raise RuntimeError("QEMU command unexpectedly contains disk or passthrough options")
        if command[command.index("-nic") + 1] != "none":
            raise RuntimeError("QEMU guest network must be disabled")

        result = run_bounded_process(
            command,
            timeout_seconds=QEMU_TIMEOUT_SECONDS,
            marker=REPORT_END,
            max_stdout_bytes=2 * 1024 * 1024,
            max_stderr_bytes=256 * 1024,
        )
        serial = result.stdout_tail.decode("utf-8", errors="replace")
        stderr = result.stderr_tail.decode("utf-8", errors="replace")
        if result.timed_out:
            raise RuntimeError(
                f"QEMU guest timed out after {QEMU_TIMEOUT_SECONDS}s; serial tail: {serial[-1800:]}"
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"QEMU exited with {result.returncode}; stderr: {stderr[-1200:]}; "
                f"serial: {serial[-1800:]}"
            )
        if result.stdout_truncated or result.stderr_truncated:
            raise RuntimeError("QEMU output exceeded bounded capture; refusing an incomplete report")
        if not result.marker_seen:
            serial_first = serial[:10000]
            serial_last = serial[-6000:]
            raise RuntimeError(
                f"guest did not emit {REPORT_END}; serial_bytes={result.stdout_bytes_seen}; "
                f"stdout_truncated={result.stdout_truncated}; stderr: {stderr[-1200:]}\n"
                f"serial first bytes:\n{serial_first}\nserial tail:\n{serial_last}"
            )

        try:
            report = _decode_guest_report(serial)
        except RuntimeError as exc:
            lines = serial.replace(chr(13), chr(10)).splitlines()
            diagnostic_lines = []
            for line in lines[-60:]:
                if REPORT_PREFIX in line:
                    payload_part = line.split(REPORT_PREFIX, 1)[1]
                    diagnostic_lines.append(
                        f"{REPORT_PREFIX}[payload redacted; chars={len(payload_part)}]"
                    )
                else:
                    diagnostic_lines.append(line[:500])
            raise RuntimeError(
                f"{exc}; guest serial diagnostics (report payload redacted):\n"
                + "\n".join(diagnostic_lines)
                + f"\nQEMU stderr tail: {stderr[-1200:]}"
            ) from exc
        device_count, functional_test_count = _validate_report(report)
        print(
            "PASS: actual wsm_hwcheck ran inside a QEMU TCG guest and its report "
            "validated against schemas/hardware-report.schema.json"
        )
        print(
            f"CPython 3.11.18 tag={PYTHON_TAG}; external ELF libraries copied={dependency_count}; "
            f"guest devices={device_count}; functional tests={functional_test_count}"
        )
        print(
            f"Guest kernel={report['environment']['kernel_release']}; "
            f"virtualization={report['environment']['virtualization']}; "
            "network_requests_performed=false; network_upload_performed=false"
        )
        print(
            f"QEMU isolation: TCG=true; network=false; virtual_disk=false; "
            f"host_passthrough=false; serial_bytes={result.stdout_bytes_seen}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
