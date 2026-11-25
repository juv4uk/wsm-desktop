#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only CXL sysfs enumeration inside a disposable QEMU Linux guest.

The host only resolves and copies the selected kernel's CXL module dependency
closure. No host modules are loaded and no host sysfs attributes are written.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

MODULES = ("cxl_acpi", "cxl_pci", "cxl_mem", "cxl_port")
MAX_MODULE_COUNT = 128
MAX_EXPANDED_MODULE_BYTES = 128 * 1024 * 1024
MAX_SERIAL_BYTES = 64 * 1024


class ProbeError(RuntimeError):
    """Raised when the disposable guest cannot safely enumerate CXL."""


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def resolve_module_dependencies(kernel_release: str) -> list[Path]:
    """Resolve the exact kernel module closure without loading any host module."""
    modprobe = shutil.which("modprobe")
    if not modprobe:
        raise ProbeError("modprobe is required to resolve CXL module dependencies")
    module_root = (Path("/lib/modules") / kernel_release).resolve()
    paths: list[Path] = []
    # modprobe accepts one target module per invocation. Resolve each driver
    # separately and merge the ordered dependency closures.
    for module in MODULES:
        result = run(
            [modprobe, "--show-depends", "--set-version", kernel_release, module],
            timeout=20,
        )
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] != "insmod":
                continue
            source = Path(fields[1]).resolve()
            try:
                source.relative_to(module_root)
            except ValueError as exc:
                raise ProbeError("modprobe returned a module outside the selected kernel tree") from exc
            if source not in paths:
                paths.append(source)
    if not paths:
        raise ProbeError("modprobe found no loadable CXL modules")
    if len(paths) > MAX_MODULE_COUNT:
        raise ProbeError("CXL dependency closure exceeds the module-count limit")
    return paths


def copy_module(source: Path, destination: Path) -> int:
    """Copy one kernel module into initramfs, decompressing its package suffix."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.name.endswith(".ko.zst"):
        tool = shutil.which("zstd")
        if not tool:
            raise ProbeError("zstd is required to unpack the runner's CXL modules")
        with destination.open("wb") as output:
            subprocess.run(
                [tool, "-d", "-q", "-c", str(source)],
                check=True,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=20,
            )
    elif source.name.endswith(".ko.xz"):
        tool = shutil.which("xz")
        if not tool:
            raise ProbeError("xz is required to unpack the selected kernel modules")
        with destination.open("wb") as output:
            subprocess.run(
                [tool, "-d", "-c", str(source)],
                check=True,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=20,
            )
    elif source.name.endswith(".ko.gz"):
        tool = shutil.which("gzip")
        if not tool:
            raise ProbeError("gzip is required to unpack the selected kernel modules")
        with destination.open("wb") as output:
            subprocess.run(
                [tool, "-d", "-c", str(source)],
                check=True,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=20,
            )
    else:
        shutil.copy2(source, destination)
    size = destination.stat().st_size
    if size <= 0:
        raise ProbeError("decompressed kernel module is empty")
    return size


def render_init(load_paths: list[str]) -> str:
    module_list = "\n".join(load_paths)
    return """#!/bin/busybox sh
exec >/dev/ttyS0 2>&1
set -eu

/bin/busybox mount -t proc -o ro proc /proc
/bin/busybox mount -t sysfs -o ro sysfs /sys

echo WSM_CXL_GUEST_BEGIN
echo WSM_CXL_KERNEL=$(cat /proc/sys/kernel/osrelease)

module_failed=0
while IFS= read -r module; do
    [ -n "$module" ] || continue
    echo WSM_CXL_MODULE_ATTEMPT=$(/bin/busybox basename "$module")
    if ! /bin/busybox insmod "$module"; then
        echo WSM_CXL_MODULE_LOAD_ERROR
        module_failed=1
    fi
done <<'WSM_MODULES'
""" + module_list + """
WSM_MODULES

/bin/busybox sleep 2
node_count=0
memdev_count=0
if [ -r /sys/firmware/acpi/tables/CEDT ]; then
    value=$(/bin/busybox wc -c </sys/firmware/acpi/tables/CEDT)
    echo WSM_CXL_CEDT_BYTES=$value
else
    echo WSM_CXL_CEDT_ABSENT
fi
acpi0017_count=0
for node in /sys/bus/acpi/devices/ACPI0017:*; do
    [ -e "$node" ] || [ -L "$node" ] || continue
    acpi0017_count=$((acpi0017_count + 1))
done
echo WSM_CXL_ACPI0017_COUNT=$acpi0017_count
for module in cxl_core cxl_acpi cxl_pci cxl_mem cxl_port; do
    if [ -d "/sys/module/$module" ]; then
        echo WSM_CXL_MODULE_LOADED=$module
    else
        echo WSM_CXL_MODULE_MISSING=$module
        module_failed=1
    fi
done
if [ -d /sys/bus/cxl/devices ]; then
    for node in /sys/bus/cxl/devices/*; do
        [ -e "$node" ] || [ -L "$node" ] || continue
        name=$(/bin/busybox basename "$node")
        node_count=$((node_count + 1))
        echo WSM_CXL_NODE=$name
        case "$name" in
            mem[0-9]*) memdev_count=$((memdev_count + 1));;
        esac
        if [ -r "$node/devtype" ]; then
            value=$(/bin/busybox cat "$node/devtype" 2>/dev/null || true)
            echo WSM_CXL_DEVTYPE=$name:$value
        fi
    done
else
    echo WSM_CXL_BUS_ABSENT
fi
echo WSM_CXL_DMESG_BEGIN
/bin/busybox dmesg | /bin/busybox grep -i cxl | /bin/busybox tail -n 80 || true
echo WSM_CXL_DMESG_END
echo WSM_CXL_NODE_COUNT=$node_count
echo WSM_CXL_MEMDEV_COUNT=$memdev_count
echo WSM_CXL_MODULE_FAILED=$module_failed
echo WSM_CXL_GUEST_END
/bin/busybox sync
/bin/busybox poweroff -f
"""


def build_initramfs(kernel_release: str, modules: list[Path], work: Path) -> tuple[Path, int]:
    root = work / "rootfs"
    for name in ("bin", "dev", "proc", "sys", "tmp", "lib/modules"):
        (root / name).mkdir(parents=True, exist_ok=True)

    busybox = shutil.which("busybox")
    if not busybox:
        raise ProbeError("busybox-static is required")
    shutil.copy2(busybox, root / "bin/busybox")
    for applet in ("sh", "mount", "insmod", "sleep", "cat", "basename", "sync", "poweroff", "dmesg", "grep", "tail", "wc"):
        link = root / "bin" / applet
        if not link.exists():
            link.symlink_to("busybox")

    for name, major, minor, mode in (
        ("console", 5, 1, "600"),
        ("ttyS0", 4, 64, "600"),
        ("null", 1, 3, "666"),
    ):
        subprocess.run(
            ["sudo", "mknod", "-m", mode, str(root / "dev" / name), "c", str(major), str(minor)],
            check=True,
            capture_output=True,
            timeout=5,
        )

    source_root = (Path("/lib/modules") / kernel_release).resolve()
    target_root = root / "lib" / "modules" / kernel_release
    guest_load_paths: list[str] = []
    expanded_bytes = 0
    for source in modules:
        relative = source.relative_to(source_root)
        for suffix in (".zst", ".xz", ".gz"):
            if relative.name.endswith(suffix):
                relative = relative.with_suffix("")
                break
        destination = target_root / relative
        expanded_bytes += copy_module(source, destination)
        if expanded_bytes > MAX_EXPANDED_MODULE_BYTES:
            raise ProbeError("expanded CXL module dependency closure exceeds 128 MiB")
        guest_load_paths.append("/lib/modules/" + kernel_release + "/" + relative.as_posix())

    init = root / "init"
    init.write_text(render_init(guest_load_paths), encoding="utf-8")
    init.chmod(0o755)

    archive = work / "cxl-guest-initramfs.cpio.gz"
    find = subprocess.Popen(
        ["find", ".", "-print0"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert find.stdout is not None
    cpio = subprocess.Popen(
        ["cpio", "--null", "-o", "-H", "newc"],
        cwd=root,
        stdin=find.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    find.stdout.close()
    assert cpio.stdout is not None
    with archive.open("wb") as output:
        gzip = shutil.which("gzip")
        if not gzip:
            raise ProbeError("gzip is required")
        pack = subprocess.Popen([gzip, "-n"], stdin=cpio.stdout, stdout=output, stderr=subprocess.PIPE)
        cpio.stdout.close()
        _, pack_error = pack.communicate(timeout=20)
    _, cpio_error = cpio.communicate(timeout=20)
    _, find_error = find.communicate(timeout=20)
    if pack.returncode != 0 or cpio.returncode != 0 or find.returncode != 0:
        detail = (pack_error or b"") + (cpio_error or b"") + (find_error or b"")
        raise ProbeError("initramfs packing failed: " + detail.decode("utf-8", errors="replace")[-2000:])
    return archive, expanded_bytes


def parse_guest_output(output: str) -> dict[str, Any]:
    encoded_size = len(output.encode("utf-8", errors="replace"))
    if encoded_size > MAX_SERIAL_BYTES:
        raise ProbeError("guest serial output exceeded the 64 KiB limit")
    if "WSM_CXL_GUEST_BEGIN" not in output or "WSM_CXL_GUEST_END" not in output:
        raise ProbeError("guest did not complete the CXL sysfs enumeration markers")
    if "WSM_CXL_MODULE_LOAD_ERROR" in output or "WSM_CXL_MODULE_FAILED=1" in output:
        raise ProbeError("one or more required CXL kernel modules failed to load in the guest")

    nodes = [
        line.partition("=")[2]
        for line in output.splitlines()
        if line.startswith("WSM_CXL_NODE=")
    ]
    devtypes = [
        line.partition("=")[2]
        for line in output.splitlines()
        if line.startswith("WSM_CXL_DEVTYPE=")
    ]
    memdev_count = 0
    for line in output.splitlines():
        if line.startswith("WSM_CXL_MEMDEV_COUNT="):
            try:
                memdev_count = int(line.partition("=")[2])
            except ValueError as exc:
                raise ProbeError("guest returned an invalid CXL memdev count") from exc
    if memdev_count < 1 or not any(name.startswith("mem") for name in nodes):
        raise ProbeError(
            "guest booted but did not enumerate a CXL memdev; "
            "bounded guest diagnostics: " + repr(output[-6000:])
        )
    return {"nodes": nodes, "devtypes": devtypes, "memdev_count": memdev_count}


def run_probe(timeout_seconds: int) -> dict[str, Any]:
    kernel_release = os.uname().release
    kernel = Path("/boot") / ("vmlinuz-" + kernel_release)
    if not kernel.is_file():
        raise ProbeError("matching runner kernel image is absent: " + str(kernel))
    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        raise ProbeError("qemu-system-x86_64 is required")
    qemu_version = run([qemu, "--version"], timeout=5).stdout.splitlines()[0]
    modules = resolve_module_dependencies(kernel_release)

    with tempfile.TemporaryDirectory(prefix="wsm-cxl-guest-") as temporary:
        work = Path(temporary)
        archive, expanded_bytes = build_initramfs(kernel_release, modules, work)
        # Runner kernel images in /boot may be root-readable only. Copy the
        # exact image unchanged into the disposable workspace with read access
        # for the unprivileged QEMU process; never chmod or rewrite /boot files.
        guest_kernel = work / "vmlinuz"
        subprocess.run(
            ["sudo", "install", "-m", "0644", str(kernel), str(guest_kernel)],
            check=True,
            capture_output=True,
            timeout=15,
        )
        command = [
            qemu,
            "-machine", "q35,cxl=on",
            "-m", "4G,maxmem=8G,slots=8",
            "-smp", "2",
            "-accel", "tcg",
            "-nodefaults",
            "-display", "none",
            "-monitor", "none",
            "-serial", "stdio",
            "-no-reboot",
            "-kernel", str(guest_kernel),
            "-initrd", str(archive),
            "-append", "console=ttyS0 rdinit=/init panic=1 loglevel=4",
            "-object", "memory-backend-ram,id=vmem0,share=on,size=256M",
            "-device", "pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1",
            "-device", "cxl-rp,port=0,bus=cxl.1,id=root_port13,chassis=0,slot=2",
            "-device", "cxl-type3,bus=root_port13,volatile-memdev=vmem0,id=cxl-vmem0",
            "-M", "cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G",
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            raise ProbeError("QEMU CXL guest timed out; serial tail=" + repr(str(stdout)[-3000:])) from exc

        output = result.stdout[-MAX_SERIAL_BYTES:]
        if result.returncode != 0:
            raise ProbeError(
                "QEMU guest returned " + str(result.returncode)
                + "; serial tail=" + repr(output[-3000:])
                + "; stderr tail=" + repr(result.stderr[-1500:])
            )
        observed = parse_guest_output(output)

    return {
        "qemu_version": qemu_version,
        "kernel_release": kernel_release,
        "guest_sysfs_enumeration": "observed",
        "cxl_nodes": observed["nodes"],
        "cxl_devtypes": observed["devtypes"],
        "cxl_memdev_count": observed["memdev_count"],
        "decompressed_module_count": len(modules),
        "decompressed_module_bytes": expanded_bytes,
        "cxl_region_created": False,
        "safety": {
            "qemu_tcg": True,
            "virtual_disk": False,
            "network": False,
            "host_passthrough": False,
            "host_modules_loaded": False,
            "host_sysfs_written": False,
            "cxl_region_created": False,
            "sysfs_mount_read_only": True,
        },
        "interpretation": (
            "A disposable Linux guest enumerated a synthetic CXL Type 3 memory device. "
            "No CXL region was created; this does not prove physical CXL compatibility, "
            "cache coherency, functional memory use, or reliability operations."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    try:
        report = run_probe(args.timeout)
    except (OSError, subprocess.SubprocessError, ProbeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "success", **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
