#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only feasibility probe for QEMU CXL Type 3 emulation.

This probe creates only an in-memory QEMU device tree. It does not boot a guest,
load kernel modules, access host devices, create a disk, or configure real CXL.
"""

from __future__ import annotations

import json
import os
import shutil
import selectors
import subprocess
import time
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_CONFIG = (
    "CONFIG_CXL_BUS",
    "CONFIG_CXL_PCI",
    "CONFIG_CXL_ACPI",
    "CONFIG_CXL_MEM",
    "CONFIG_CXL_PORT",
    "CONFIG_CXL_REGION",
)
OPTIONAL_CONFIG = ("CONFIG_CXL_PMEM",)
CXL_MODULES = (
    "cxl_core",
    "cxl_pci",
    "cxl_acpi",
    "cxl_mem",
    "cxl_port",
    "cxl_region",
    "cxl_pmem",
    "cxl_test",
)
CONFIG_MODULES = {
    "CONFIG_CXL_BUS": "cxl_core",
    "CONFIG_CXL_PCI": "cxl_pci",
    "CONFIG_CXL_ACPI": "cxl_acpi",
    "CONFIG_CXL_MEM": "cxl_mem",
    "CONFIG_CXL_PORT": "cxl_port",
    "CONFIG_CXL_REGION": "cxl_region",
}
QEMU_TIMEOUT_SECONDS = 20
MAX_CAPTURE_BYTES = 64 * 1024


def parse_kernel_config(text: str) -> dict[str, str]:
    """Return normalized CONFIG_* values; absent and not-set remain distinct."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value.strip().strip('"')
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            name = line[2:].split(" ", 1)[0]
            values[name] = "n"
    return values


def read_kernel_config(kernel_release: str) -> tuple[dict[str, str], str | None]:
    candidates = (
        Path("/boot") / f"config-{kernel_release}",
        Path("/proc/config.gz"),
    )
    for candidate in candidates:
        try:
            if candidate.name == "config.gz":
                import gzip

                raw = gzip.decompress(candidate.read_bytes()).decode("utf-8", errors="replace")
            else:
                raw = candidate.read_text(encoding="utf-8", errors="replace")
            return parse_kernel_config(raw), str(candidate)
        except OSError:
            continue
    return {}, None


def find_kernel_modules(kernel_release: str) -> dict[str, list[str]]:
    root = Path("/lib/modules") / kernel_release
    found: dict[str, list[str]] = {}
    if not root.is_dir():
        return found
    for module in CXL_MODULES:
        paths = []
        for suffix in (".ko", ".ko.xz", ".ko.zst", ".ko.gz"):
            paths.extend(str(path.relative_to(root)) for path in root.rglob(module + suffix))
        if paths:
            found[module] = sorted(paths)
    return found


def build_qemu_command(qemu: str) -> list[str]:
    """Build the QEMU manual's one-device CXL 2.0 Type-3 volatile topology."""
    return [
        qemu,
        "-S",
        "-nodefaults",
        "-display", "none",
        "-machine", "q35,cxl=on",
        "-accel", "tcg",
        "-m", "1G,maxmem=2G,slots=8",
        "-smp", "1",
        "-object", "memory-backend-ram,id=vmem0,size=256M,share=on",
        "-device", "pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1",
        "-device", "cxl-rp,port=0,bus=cxl.1,id=root_port0,chassis=0,slot=0",
        "-device", "cxl-type3,bus=root_port0,volatile-memdev=vmem0,id=cxl-vmem0",
        "-machine", "cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G",
        "-monitor", "stdio",
    ]


def run_bounded_command(
    command: list[str],
    *,
    input_data: bytes,
    max_output_bytes: int,
    timeout_seconds: float,
) -> tuple[str, int | None, str]:
    """Run a small monitor command with a hard combined stdout/stderr ceiling."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        close_fds=True,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise OSError("QEMU monitor pipes were not created")
    try:
        try:
            process.stdin.write(input_data)
            process.stdin.flush()
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()

        selector = selectors.DefaultSelector()
        outputs = {"stdout": bytearray(), "stderr": bytearray()}
        total_seen = 0
        deadline = time.monotonic() + timeout_seconds
        timed_out = False
        overflow = False
        streams = ((process.stdout, "stdout"), (process.stderr, "stderr"))
        try:
            for stream, name in streams:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                if selector.get_map():
                    events = selector.select(min(0.1, remaining))
                else:
                    time.sleep(min(0.02, remaining))
                    events = ()
                for key, _ in events:
                    try:
                        chunk = os.read(key.fd, min(4096, max_output_bytes + 1 - total_seen))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    total_seen += len(chunk)
                    if total_seen > max_output_bytes:
                        overflow = True
                        break
                    outputs[key.data].extend(chunk)
                if overflow:
                    break
        finally:
            selector.close()

        if overflow or timed_out:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            status = "output-limit-exceeded" if overflow else "timeout"
            return status, process.returncode, ""
        returncode = process.wait(timeout=1)
        output = (
            outputs["stdout"].decode("utf-8", errors="replace")
            + "\\n"
            + outputs["stderr"].decode("utf-8", errors="replace")
        )
        return "completed", returncode, output
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def run_qemu_topology_probe(qemu: str) -> dict[str, object]:
    command = build_qemu_command(qemu)
    try:
        execution, returncode, output = run_bounded_command(
            command,
            input_data=b"info qtree\\ninfo pci\\nquit\\n",
            max_output_bytes=MAX_CAPTURE_BYTES,
            timeout_seconds=QEMU_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return {
            "status": "launch-error",
            "exit_code": None,
            "devices_seen": [],
            "diagnostic": type(exc).__name__,
        }
    if execution == "timeout":
        return {
            "status": "timeout",
            "exit_code": returncode,
            "devices_seen": [],
            "diagnostic": "QEMU did not answer the in-memory monitor probe within 20 seconds.",
        }
    if execution == "output-limit-exceeded":
        return {
            "status": "output-limit-exceeded",
            "exit_code": returncode,
            "devices_seen": [],
            "diagnostic": f"QEMU probe output exceeded the {MAX_CAPTURE_BYTES}-byte streaming limit.",
        }

    expected = ("cxl.1", "root_port0", "cxl-vmem0")
    devices_seen = [device for device in expected if device in output]
    unsupported = (
        "unsupported" in output.casefold()
        or "not found" in output.casefold()
        or "Property 'CXL" in output
    )
    if returncode == 0 and len(devices_seen) == len(expected):
        status = "type3-topology-instantiated"
    elif unsupported:
        status = "cxl-device-or-machine-unsupported"
    else:
        status = "topology-probe-failed"

    return {
        "status": status,
        "exit_code": returncode,
        "devices_seen": devices_seen,
        "diagnostic": output[-6000:],
    }


def probe(qemu_override: str | None = None) -> dict[str, object]:
    qemu = qemu_override or shutil.which("qemu-system-x86_64")
    kernel_release = os.uname().release
    config, config_source = read_kernel_config(kernel_release)
    modules = find_kernel_modules(kernel_release)
    config_support = {
        name: config.get(name, "unknown")
        for name in (*REQUIRED_CONFIG, *OPTIONAL_CONFIG)
    }
    driver_ready = all(
        config.get(name) == "y"
        or (
            config.get(name) == "m"
            and CONFIG_MODULES.get(name) in modules
        )
        for name in REQUIRED_CONFIG
    )
    qemu_version = None
    qemu_result: dict[str, object] = {
        "status": "qemu-not-found",
        "exit_code": None,
        "devices_seen": [],
        "diagnostic": "qemu-system-x86_64 was not found.",
    }
    if qemu:
        try:
            version = subprocess.run(
                [qemu, "--version"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=5,
                check=False,
            )
            qemu_version = (version.stdout or version.stderr).splitlines()[0:1]
        except (OSError, subprocess.TimeoutExpired) as exc:
            qemu_result = {
                "status": "version-probe-failed",
                "exit_code": None,
                "devices_seen": [],
                "diagnostic": f"{type(exc).__name__}: {exc}",
            }
        else:
            qemu_result = run_qemu_topology_probe(qemu)

    return {
        "probe_version": "0.1.0",
        "scope": "QEMU CXL device-tree feasibility only; no guest boot or CXL driver claims",
        "host_kernel_release": kernel_release,
        "host_kernel_config_source": config_source,
        "cxl_kernel_config": config_support,
        "cxl_modules_found": modules,
        "guest_cxl_driver_config_sufficient_for_followup": driver_ready,
        "qemu_binary": qemu,
        "qemu_version": qemu_version[0] if qemu_version else None,
        "qemu_cxl_probe": qemu_result,
        "isolation": {
            "qemu_paused_before_guest_execution": True,
            "host_disk_attached": False,
            "network_device_attached": False,
            "host_device_passthrough": False,
            "host_kernel_modules_loaded_or_unloaded": False,
            "host_sysfs_written": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    qemu = args[args.index("--qemu") + 1] if "--qemu" in args and args.index("--qemu") + 1 < len(args) else None
    result = probe(qemu)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
