# SPDX-License-Identifier: LicenseRef-Volnist
"""Turn a partition layout into an ordered list of steps. Emit, never run.

`partition.py` answers "what should the disk look like". This module answers the
next question: what has to happen, in what order, to get from that layout to a
mounted target that `guix system init` can write into.

Everything here is data. No function opens a device, formats anything or mounts
anything. The caller decides, one step at a time.

The ordering matters and is the whole point:

1. re-read the partition table - the kernel does not always notice new
   partitions on its own, and formatting a stale device node formats the wrong
   thing;
2. format the ESP and the root;
3. mount root, then the ESP *inside* it - a bootloader installed into an ESP
   that is not part of the target tree lands on the live system;
4. only then hand the target to the backend.

What this module deliberately does not decide: which filesystem the user wants.
ext4 is the default because it is boring and every recovery tool knows it. btrfs
is a legitimate choice with real advantages (snapshots, compression) and real
costs (more moving parts, more ways to be surprised). That is the user's call,
not a default I should smuggle in.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from wsm_install.backend_guix import (
    GUIX_CHANNEL_LOCK_PATH,
    GUIX_CONFIGURATION_PATH,
    GUIX_TARGET_MOUNTPOINT,
    build_argv,
)
from wsm_install.partition import DEVICE_PATH, Layout, Refused

TARGET_MOUNTPOINT = GUIX_TARGET_MOUNTPOINT
SYSTEM_CONFIG_PATH = GUIX_CONFIGURATION_PATH
CHANNEL_LOCK_PATH = GUIX_CHANNEL_LOCK_PATH

# Absolute paths for every tool a privileged step runs.
#
# This is a direct lesson from Omarchy 4.0.0: their privileged DNS helper ran
# with an inherited PATH, and a user-writable directory earlier in PATH could
# supply a file named like a standard utility that then executed as root
# (fix #8172). The same shape applies here - these steps are meant to be run as
# root - so no step may rely on PATH lookup at all.
TRUSTED_TOOLS = {
    "sgdisk": "/usr/sbin/sgdisk",
    "partprobe": "/usr/sbin/partprobe",
    "udevadm": "/usr/bin/udevadm",
    "mkfs.ext4": "/usr/sbin/mkfs.ext4",
    "mkfs.btrfs": "/usr/sbin/mkfs.btrfs",
    "mkfs.xfs": "/usr/sbin/mkfs.xfs",
    "mkfs.fat": "/usr/sbin/mkfs.fat",
    "mount": "/usr/bin/mount",
    "mkdir": "/usr/bin/mkdir",
}

FILESYSTEMS = {
    "ext4": {"mkfs": "mkfs.ext4", "args": ["-F"], "root": True},
    "btrfs": {"mkfs": "mkfs.btrfs", "args": ["-f"], "root": True},
    "xfs": {"mkfs": "mkfs.xfs", "args": ["-f"], "root": True},
}


@dataclass
class Step:
    """One shell command plus why it exists. `destructive` is not decoration."""

    command: list[str]
    purpose: str
    destructive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "purpose": self.purpose,
            "destructive": self.destructive,
        }


def _validate_layout_confirmation(layout: Layout) -> None:
    if not DEVICE_PATH.fullmatch(layout.disk):
        raise Refused("disk.path", f"{layout.disk!r} is not an allow-listed whole block device")
    if (
        isinstance(layout.disk_size_bytes, bool)
        or not isinstance(layout.disk_size_bytes, int)
        or layout.disk_size_bytes <= 0
    ):
        raise Refused("disk.size-unrecorded", "layout does not retain the observed disk size")
    if layout.acknowledgement != layout.disk:
        raise Refused(
            "disk.acknowledgement",
            "the layout no longer carries the acknowledgement naming its exact target disk",
        )


def _validate_target(target: str) -> None:
    if target != TARGET_MOUNTPOINT:
        raise Refused(
            "target.fixed",
            f"target must be exactly {TARGET_MOUNTPOINT!r}, got {target!r}",
        )


def _partition_by_role(layout: Layout, role: str) -> dict[str, Any]:
    for partition in layout.partitions:
        if partition["role"] == role:
            return partition
    raise Refused("layout.role-missing", f"layout has no partition with role {role!r}")


def device_for(disk: str, number: int) -> str:
    """Name a partition device using an allow-listed whole-disk path."""
    if not DEVICE_PATH.fullmatch(disk):
        raise Refused("disk.path", f"{disk!r} is not an allow-listed whole block device")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise Refused("partition.number", f"partition number must be positive, got {number!r}")
    if disk[-1].isdigit():
        return f"{disk}p{number}"
    return f"{disk}{number}"


def plan_steps(
    layout: Layout,
    filesystem: str = "ext4",
    target: str = TARGET_MOUNTPOINT,
    hostname: str | None = None,
) -> list[Step]:
    """Build a non-executable ordered plan, or refuse.

    Layout.commands() describes GPT mutations. Include them before partprobe:
    partprobe only re-reads a partition table; it cannot create one.
    """
    _validate_layout_confirmation(layout)
    _validate_target(target)

    if filesystem not in FILESYSTEMS:
        raise Refused(
            "filesystem.unsupported",
            f"{filesystem!r} is not supported; choose one of {sorted(FILESYSTEMS)}",
        )
    if layout.firmware not in {"uefi", "bios"}:
        raise Refused("disk.firmware", f"unsupported firmware mode {layout.firmware!r}")

    root = _partition_by_role(layout, "root")
    esp = _partition_by_role(layout, "esp") if layout.firmware == "uefi" else None
    if layout.firmware == "bios":
        _partition_by_role(layout, "bios-grub")

    root_device = device_for(layout.disk, root.get("number"))
    esp_device = device_for(layout.disk, esp.get("number")) if esp is not None else None

    steps: list[Step] = []
    for index, raw_command in enumerate(layout.commands()):
        if not raw_command or raw_command[0] != "sgdisk" or raw_command[-1] != layout.disk:
            raise Refused("layout.command", "partition layout contains an unexpected disk command")
        command = [TRUSTED_TOOLS["sgdisk"], *raw_command[1:]]
        purpose = (
            "erase the existing partition table before creating the requested GPT layout"
            if index == 0 and "--zap-all" in raw_command
            else "create or define a partition in the requested GPT layout"
        )
        steps.append(Step(command, purpose, destructive=True))

    steps.extend([
        Step(
            [TRUSTED_TOOLS["partprobe"], layout.disk],
            "ask the kernel to re-read the newly written partition table",
        ),
        Step(
            [TRUSTED_TOOLS["udevadm"], "settle"],
            "wait for partition device nodes to appear before formatting",
        ),
        Step(
            [TRUSTED_TOOLS[FILESYSTEMS[filesystem]["mkfs"]],
             *FILESYSTEMS[filesystem]["args"], root_device],
            f"create {filesystem} on the root partition",
            destructive=True,
        ),
    ])

    if esp_device is not None:
        steps.append(
            Step(
                [TRUSTED_TOOLS["mkfs.fat"], "-F", "32", esp_device],
                "format the EFI system partition as FAT32",
                destructive=True,
            )
        )

    steps.append(
        Step(
            [TRUSTED_TOOLS["mount"], root_device, TARGET_MOUNTPOINT],
            "mount the root filesystem in the fixed target",
        )
    )

    if esp_device is not None:
        steps.extend([
            Step(
                [TRUSTED_TOOLS["mkdir"], "-p", f"{TARGET_MOUNTPOINT}/boot/efi"],
                "create the ESP mount point inside the target tree",
            ),
            Step(
                [TRUSTED_TOOLS["mount"], esp_device, f"{TARGET_MOUNTPOINT}/boot/efi"],
                "mount the ESP inside the target tree, not on the live system",
            ),
        ])

    return steps


def backend_command(
    layout: Layout,
    system_file: str = SYSTEM_CONFIG_PATH,
    target: str = TARGET_MOUNTPOINT,
) -> list[str]:
    """Return a fixed, lock-pinned Guix argv. Never execute it here."""
    _validate_layout_confirmation(layout)
    _validate_target(target)
    if system_file != SYSTEM_CONFIG_PATH:
        raise Refused(
            "backend.system-file",
            f"system configuration path must be exactly {SYSTEM_CONFIG_PATH!r}",
        )
    return list(build_argv(SYSTEM_CONFIG_PATH, TARGET_MOUNTPOINT))


def render(steps: list[Step], command: list[str]) -> str:
    lines = ["# NOT EXECUTED - review every line before running anything", ""]
    for step in steps:
        marker = "DESTRUCTIVE" if step.destructive else "safe"
        lines.append(f"# [{marker}] {step.purpose}")
        lines.append(shlex.join(step.command))
        lines.append("")
    lines.append("# handoff to the backend")
    lines.append(shlex.join(command))
    return "\n".join(lines) + "\n"
