#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe QEMU CXL Type 3 model support without booting a guest.

This is a feasibility check only. It creates a paused QEMU process with one
volatile CXL Type 3 device, inspects its QEMU object tree over a local QMP
Unix socket, and exits. It does not configure a CXL region or touch host
devices, disks, network interfaces, or hardware.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any

REQUIRED_CONFIG = (
    "CONFIG_CXL_BUS",
    "CONFIG_CXL_PCI",
    "CONFIG_CXL_ACPI",
    "CONFIG_CXL_MEM",
    "CONFIG_CXL_PORT",
    "CONFIG_CXL_REGION",
)


class ProbeError(RuntimeError):
    """Raised when the QEMU CXL model cannot be instantiated or inspected."""


def read_kernel_config(kernel_release: str) -> dict[str, str] | None:
    """Read the exact running kernel config, if the runner exposes it."""
    candidates = (
        Path("/boot") / f"config-{kernel_release}",
        Path("/usr/lib/modules") / kernel_release / "build" / ".config",
    )
    for candidate in candidates:
        if candidate.is_file():
            return parse_kernel_config(candidate.read_text(encoding="utf-8", errors="replace"))

    proc_config = Path("/proc/config.gz")
    if proc_config.is_file():
        with gzip.open(proc_config, "rt", encoding="utf-8", errors="replace") as stream:
            return parse_kernel_config(stream.read())
    return None


def parse_kernel_config(text: str) -> dict[str, str]:
    """Return CONFIG_* assignments, preserving y/m/not-set distinctly."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("# CONFIG_") and line.endswith(" is not set"):
            key = line[len("# "):].removesuffix(" is not set")
            values[key] = "n"
        elif line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values


class QMPClient:
    """Buffered QMP JSON-line client that preserves coalesced socket frames."""

    MAX_LINE_BYTES = 1024 * 1024

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._buffer = bytearray()

    def read_line(self, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
        """Read one bounded JSON line without discarding following frames."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                if newline > self.MAX_LINE_BYTES:
                    raise ProbeError("QMP response exceeded the 1 MiB line limit")
                line = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                try:
                    decoded = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ProbeError(f"QMP returned invalid JSON: {exc}") from exc
                if not isinstance(decoded, dict):
                    raise ProbeError("QMP response is not a JSON object")
                return decoded

            if len(self._buffer) > self.MAX_LINE_BYTES:
                raise ProbeError("QMP response exceeded the 1 MiB line limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError(f"QMP response timed out after {timeout_seconds}s")
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(min(4096, self.MAX_LINE_BYTES + 1 - len(self._buffer)))
            except socket.timeout as exc:
                raise ProbeError(f"QMP response timed out after {timeout_seconds}s") from exc
            if not chunk:
                raise ProbeError("QMP socket closed before a complete response")
            self._buffer.extend(chunk)

    def execute(self, command: str, arguments: dict[str, Any] | None = None) -> Any:
        """Execute one QMP command and skip asynchronous event messages."""
        request: dict[str, Any] = {"execute": command}
        if arguments is not None:
            request["arguments"] = arguments
        self.sock.sendall(
            json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\r\n"
        )
        while True:
            response = self.read_line()
            if "event" in response:
                continue
            if "error" in response:
                raise ProbeError(f"QMP command {command!r} failed: {response['error']}")
            if "return" not in response:
                raise ProbeError(f"QMP command {command!r} returned an unexpected message")
            return response["return"]

def wait_for_qmp(
    socket_path: Path,
    process: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
) -> socket.socket:
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeError(f"QEMU exited before QMP became ready (exit={process.returncode})")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.connect(str(socket_path))
            return client
        except OSError as exc:
            last_error = exc
            client.close()
            time.sleep(0.05)
    raise ProbeError(f"QMP did not become ready within {timeout_seconds}s: {last_error}")


def kernel_module_status(module: str, kernel_release: str) -> dict[str, str]:
    """Observe module availability without loading or changing kernel state."""
    modinfo = shutil.which("modinfo")
    if not modinfo:
        return {"status": "tool-unavailable"}
    result = subprocess.run(
        [modinfo, "-k", kernel_release, "-F", "filename", module],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return {"status": "module-file", "path": result.stdout.strip().splitlines()[0]}
    if result.returncode != 0:
        return {"status": "not-found"}
    return {"status": "unknown"}


def run_probe(qemu: str, *, timeout_seconds: float) -> dict[str, Any]:
    version = subprocess.run(
        [qemu, "--version"], check=True, capture_output=True, text=True, timeout=5
    ).stdout.splitlines()[0]
    kernel_release = os.uname().release
    config = read_kernel_config(kernel_release)
    config_summary = (
        {key: config.get(key, "absent") for key in REQUIRED_CONFIG}
        if config is not None
        else None
    )
    modules = {
        name: kernel_module_status(name, kernel_release)
        for name in ("cxl_core", "cxl_pci", "cxl_acpi", "cxl_mem", "cxl_port")
    }

    with tempfile.TemporaryDirectory(prefix="wsm-cxl-qemu-") as temporary:
        root = Path(temporary)
        qmp_path = root / "qmp.sock"
        log_path = root / "qemu.log"
        command = [
            qemu,
            "-machine", "q35,cxl=on",
            "-m", "4G,maxmem=8G,slots=8",
            "-smp", "2",
            "-accel", "tcg",
            "-nodefaults",
            "-display", "none",
            "-monitor", "none",
            "-serial", "none",
            "-S",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
            "-object", "memory-backend-ram,id=vmem0,share=on,size=256M",
            "-device", "pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1",
            "-device", "cxl-rp,port=0,bus=cxl.1,id=root_port13,chassis=0,slot=2",
            "-device", "cxl-type3,bus=root_port13,volatile-memdev=vmem0,id=cxl-vmem0",
            "-M", "cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G",
        ]
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                client = wait_for_qmp(qmp_path, process, timeout_seconds=timeout_seconds)
                with client:
                    qmp = QMPClient(client)
                    greeting = qmp.read_line()
                    if "QMP" not in greeting:
                        raise ProbeError("QMP greeting is missing the QMP capability object")
                    qmp.execute("qmp_capabilities")
                    tree = qmp.execute(
                        "human-monitor-command",
                        {"command-line": "info qtree"},
                    )
                    if not isinstance(tree, str):
                        raise ProbeError("QEMU info qtree did not return text")
                    if "cxl-vmem0" not in tree or "cxl-type3" not in tree:
                        raise ProbeError("QEMU started but the expected CXL Type 3 device is absent from info qtree")
                    device_seen = True
            except Exception as exc:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise ProbeError(f"{exc}\nBounded QEMU log tail:\n{tail}") from exc
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)

    return {
        "qemu_version": version,
        "qemu_cxl_type3_model": "instantiated",
        "qemu_device_id": "cxl-vmem0",
        "qemu_machine": "q35,cxl=on",
        "acceleration": "tcg",
        "guest_booted": False,
        "guest_sysfs_enumeration": "not-tested",
        "cxl_region_created": False,
        "kernel_release": kernel_release,
        "kernel_config": config_summary,
        "kernel_modules": modules,
        "safety": {
            "virtual_disk": False,
            "network": False,
            "host_passthrough": False,
            "guest_boot": False,
            "host_modules_loaded": False,
            "host_devices_changed": False,
        },
        "interpretation": (
            "QEMU device-model construction only; this does not prove Linux guest "
            "sysfs enumeration, CXL region activation, cache coherency, or physical hardware support."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default=shutil.which("qemu-system-x86_64") or "qemu-system-x86_64")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    try:
        result = run_probe(args.qemu, timeout_seconds=args.timeout)
    except (OSError, subprocess.SubprocessError, ProbeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "success", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
