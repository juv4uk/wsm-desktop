#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only CXL sysfs enumeration inside a disposable QEMU Linux guest.

The host only resolves and copies the selected kernel's CXL module dependency
closure. No host modules are loaded and no host sysfs attributes are written.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.qemu_boot_smoke import run_bounded_process

MODULES = ("cxl_acpi", "cxl_pci", "cxl_mem", "cxl_port")
MAX_MODULE_COUNT = 128
MAX_EXPANDED_MODULE_BYTES = 128 * 1024 * 1024
MAX_MODULE_ARCHIVE_BYTES = 128 * 1024 * 1024
MODULE_DECOMPRESS_CHUNK_BYTES = 64 * 1024
MODULE_DECOMPRESS_TIMEOUT_SECONDS = 20
MAX_COMMAND_STDOUT_BYTES = 256 * 1024
MAX_COMMAND_STDERR_BYTES = 16 * 1024
MAX_QEMU_STDERR_BYTES = 16 * 1024
MAX_SERIAL_BYTES = 64 * 1024
MAX_INITRAMFS_BYTES = 256 * 1024 * 1024
INITRAMFS_TIMEOUT_SECONDS = 45
PROCESS_OUTPUT_CHUNK_BYTES = 64 * 1024


class ProbeError(RuntimeError):
    """Raised when the disposable guest cannot safely enumerate CXL."""


def run(
    command: list[str],
    timeout: int = 20,
    *,
    max_stdout_bytes: int = MAX_COMMAND_STDOUT_BYTES,
    max_stderr_bytes: int = MAX_COMMAND_STDERR_BYTES,
) -> subprocess.CompletedProcess[str]:
    """Run a small host command with bounded stdout/stderr capture."""
    try:
        result = run_bounded_process(
            command,
            timeout_seconds=timeout,
            marker=None,
            max_stdout_bytes=max_stdout_bytes,
            max_stderr_bytes=max_stderr_bytes,
        )
    except (OSError, ValueError) as exc:
        raise ProbeError(f"cannot execute {command[0]!r}: {exc}") from exc

    stdout = result.stdout_tail.decode("utf-8", errors="replace")
    stderr = result.stderr_tail.decode("utf-8", errors="replace")
    if result.timed_out:
        raise ProbeError(f"command timed out after {timeout} seconds: {command[0]}")
    if result.stdout_truncated or result.stderr_truncated:
        raise ProbeError(
            f"command output exceeded bounded capture: {command[0]} "
            f"(stdout={result.stdout_bytes_seen}, stderr={result.stderr_bytes_seen})"
        )
    if result.returncode != 0:
        raise ProbeError(
            f"command failed ({result.returncode}): {command[0]}; "
            f"stderr tail={stderr[-1000:]!r}"
        )
    return subprocess.CompletedProcess(command, result.returncode, stdout, stderr)


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


def _stop_child(process: subprocess.Popen[bytes]) -> None:
    """Terminate a decompressor promptly after a budget violation or timeout."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _copy_uncompressed_module(source: Path, destination: Path, limit: int) -> int:
    """Copy an uncompressed module in chunks without crossing the byte budget."""
    total = 0
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        while True:
            remaining = limit - total
            chunk = input_stream.read(min(MODULE_DECOMPRESS_CHUNK_BYTES, remaining + 1))
            if not chunk:
                return total
            if len(chunk) > remaining:
                raise ProbeError(
                    f"expanded CXL module exceeds remaining {limit}-byte budget: {source.name}"
                )
            output_stream.write(chunk)
            total += len(chunk)


def _decompress_module_to_file(command: list[str], source: Path, destination: Path, limit: int) -> int:
    """Stream decompressor stdout directly to disk under a hard byte cap and timeout."""
    if limit < 1:
        raise ProbeError("expanded CXL module dependency budget is exhausted")

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            close_fds=True,
        )
    except OSError as exc:
        raise ProbeError(f"module decompressor is unavailable for {source.name}: {exc}") from exc

    if process.stdout is None:
        _stop_child(process)
        raise ProbeError(f"module decompressor did not provide stdout: {source.name}")

    stream = process.stdout
    selector = selectors.DefaultSelector()
    total = 0
    deadline = time.monotonic() + MODULE_DECOMPRESS_TIMEOUT_SECONDS
    try:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
        with destination.open("wb") as output_stream:
            while selector.get_map() or process.poll() is None:
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    _stop_child(process)
                    raise ProbeError(f"module decompression timed out: {source.name}")

                if selector.get_map():
                    events = selector.select(min(0.1, remaining_time))
                else:
                    time.sleep(min(0.02, remaining_time))
                    events = ()

                for key, _ in events:
                    remaining_bytes = limit - total
                    try:
                        chunk = os.read(
                            key.fd,
                            min(MODULE_DECOMPRESS_CHUNK_BYTES, remaining_bytes + 1),
                        )
                    except BlockingIOError:
                        continue

                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue

                    if len(chunk) > remaining_bytes:
                        _stop_child(process)
                        raise ProbeError(
                            f"decompressed CXL module exceeds remaining {limit}-byte budget: {source.name}"
                        )

                    output_stream.write(chunk)
                    total += len(chunk)

                if process.poll() is not None and not selector.get_map():
                    break

            try:
                returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                _stop_child(process)
                raise ProbeError(f"module decompression timed out: {source.name}") from exc

        if returncode != 0:
            raise ProbeError(f"module decompression failed for {source.name}")
        return total
    except BaseException:
        _stop_child(process)
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        selector.close()
        if not stream.closed:
            stream.close()


def copy_module(
    source: Path,
    destination: Path,
    *,
    max_output_bytes: int = MAX_EXPANDED_MODULE_BYTES,
) -> int:
    """Copy/decompress one module while enforcing compressed and expanded byte limits."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if max_output_bytes < 1:
            raise ProbeError("expanded CXL module dependency budget is exhausted")
        if source.stat().st_size > MAX_MODULE_ARCHIVE_BYTES:
            raise ProbeError(
                f"compressed CXL module archive exceeds {MAX_MODULE_ARCHIVE_BYTES} bytes: {source.name}"
            )

        if source.name.endswith(".ko.zst"):
            tool = shutil.which("zstd")
            if not tool:
                raise ProbeError("zstd is required to unpack the runner's CXL modules")
            size = _decompress_module_to_file(
                [tool, "-d", "-q", "-c", str(source)],
                source,
                destination,
                max_output_bytes,
            )
        elif source.name.endswith(".ko.xz"):
            tool = shutil.which("xz")
            if not tool:
                raise ProbeError("xz is required to unpack the selected kernel modules")
            size = _decompress_module_to_file(
                [tool, "-d", "-c", str(source)],
                source,
                destination,
                max_output_bytes,
            )
        elif source.name.endswith(".ko.gz"):
            tool = shutil.which("gzip")
            if not tool:
                raise ProbeError("gzip is required to unpack the selected kernel modules")
            size = _decompress_module_to_file(
                [tool, "-d", "-c", str(source)],
                source,
                destination,
                max_output_bytes,
            )
        else:
            size = _copy_uncompressed_module(source, destination, max_output_bytes)

        if size <= 0:
            raise ProbeError("decompressed kernel module is empty")
        return size
    except BaseException:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise


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


def run_bounded_file(
    command: list[str],
    *,
    cwd: Path,
    destination: Path,
    timeout_seconds: float,
    max_bytes: int,
) -> int:
    """Stream child stdout to a new file with hard byte and wall-clock limits."""
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
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        process.wait()
        raise ProbeError("initramfs pipeline stdout pipe was not created")

    stream = process.stdout
    selector = selectors.DefaultSelector()
    total = 0
    created = False
    deadline = time.monotonic() + timeout_seconds
    try:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
        with destination.open("xb") as output:
            created = True
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProbeError("initramfs pipeline exceeded its time limit")
                events = selector.select(min(0.1, remaining)) if selector.get_map() else ()
                if not selector.get_map() and process.poll() is None:
                    time.sleep(min(0.02, remaining))
                for key, _ in events:
                    try:
                        chunk = os.read(
                            key.fd,
                            min(PROCESS_OUTPUT_CHUNK_BYTES, max_bytes - total + 1),
                        )
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ProbeError(
                            f"initramfs output exceeded the {max_bytes}-byte ceiling"
                        )
                    output.write(chunk)

            try:
                returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise ProbeError("initramfs pipeline exceeded its time limit") from exc
        if returncode != 0:
            raise ProbeError(f"initramfs pipeline failed with exit code {returncode}")
        if total <= 0:
            raise ProbeError("initramfs pipeline produced an empty archive")
        return total
    except BaseException:
        try:
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
        if not stream.closed:
            stream.close()


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
        run(
            ["sudo", "mknod", "-m", mode, str(root / "dev" / name), "c", str(major), str(minor)],
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
        remaining_bytes = MAX_EXPANDED_MODULE_BYTES - expanded_bytes
        if remaining_bytes < 1:
            raise ProbeError("expanded CXL module dependency closure exceeds 128 MiB")
        expanded_bytes += copy_module(
            source,
            destination,
            max_output_bytes=remaining_bytes,
        )
        guest_load_paths.append("/lib/modules/" + kernel_release + "/" + relative.as_posix())

    init = root / "init"
    init.write_text(render_init(guest_load_paths), encoding="utf-8")
    init.chmod(0o755)

    archive = work / "cxl-guest-initramfs.cpio.gz"
    command = [
        "bash",
        "-o",
        "pipefail",
        "-c",
        "find . -print0 | sort -z | cpio --null -o -H newc 2>/dev/null | gzip -n",
    ]
    run_bounded_file(
        command,
        cwd=root,
        destination=archive,
        timeout_seconds=INITRAMFS_TIMEOUT_SECONDS,
        max_bytes=MAX_INITRAMFS_BYTES,
    )
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


def build_qemu_command(qemu: str, kernel: Path, initramfs: Path) -> list[str]:
    """Build an isolated QEMU command for the disposable CXL guest."""
    return [
        qemu,
        "-no-user-config",
        "-machine", "q35,cxl=on",
        "-m", "4G,maxmem=8G,slots=8",
        "-smp", "2",
        "-accel", "tcg",
        "-nodefaults",
        "-nic", "none",
        "-display", "none",
        "-monitor", "none",
        "-serial", "stdio",
        "-no-reboot",
        "-kernel", str(kernel),
        "-initrd", str(initramfs),
        "-append", "console=ttyS0 rdinit=/init panic=1 loglevel=4",
        "-object", "memory-backend-ram,id=vmem0,share=on,size=256M",
        "-device", "pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1",
        "-device", "cxl-rp,port=0,bus=cxl.1,id=root_port13,chassis=0,slot=2",
        "-device", "cxl-type3,bus=root_port13,volatile-memdev=vmem0,id=cxl-vmem0",
        "-M", "cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G",
    ]


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
        run(
            ["sudo", "install", "-m", "0644", str(kernel), str(guest_kernel)],
            timeout=15,
        )
        command = build_qemu_command(qemu, guest_kernel, archive)
        try:
            result = run_bounded_process(
                command,
                timeout_seconds=timeout_seconds,
                marker=None,
                max_stdout_bytes=MAX_SERIAL_BYTES,
                max_stderr_bytes=MAX_QEMU_STDERR_BYTES,
            )
        except (OSError, ValueError) as exc:
            raise ProbeError(f"cannot launch bounded QEMU guest process: {exc}") from exc

        output = result.stdout_tail.decode("utf-8", errors="replace")
        stderr = result.stderr_tail.decode("utf-8", errors="replace")
        if result.timed_out:
            raise ProbeError("QEMU CXL guest timed out; serial tail=" + repr(output[-3000:]))
        if result.stdout_truncated or result.stderr_truncated:
            raise ProbeError(
                "QEMU CXL guest exceeded bounded output capture "
                f"(serial={result.stdout_bytes_seen}, stderr={result.stderr_bytes_seen})"
            )
        if result.returncode != 0:
            raise ProbeError(
                "QEMU guest returned " + str(result.returncode)
                + "; serial tail=" + repr(output[-3000:])
                + "; stderr tail=" + repr(stderr[-1500:])
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