# SPDX-License-Identifier: LicenseRef-Volnist
"""Build a safe, ordered installation plan. Emit argv; never execute it.

The partition planner describes a proposed GPT layout. This module includes
those destructive table operations in the sequence before asking the kernel to
re-read the table, waiting for udev, formatting filesystems, and mounting them.

Every operation is data. No function opens a block device, executes a command,
formats a filesystem, or mounts anything. A future executor must add a separate
confirmation/revalidation gate; this module is not that executor.
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

FILESYSTEMS = {
    "ext4": {"mkfs": "mkfs.ext4", "args": ["-F"], "root": True},
    "btrfs": {"mkfs": "mkfs.btrfs", "args": ["-f"], "root": True},
    "xfs": {"mkfs": "mkfs.xfs", "args": ["-f"], "root": True},
}


@dataclass
class Step:
    """One argv command plus its purpose and whether it destroys data."""

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
        raise Refused(
            "disk.path",
            f"{layout.disk!r} is not an allow-listed whole block device",
        )
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
    """The backend contract intentionally supports exactly one mount root."""
    if target != TARGET_MOUNTPOINT:
        raise Refused(
            "target.fixed",
            f"target must be exactly {TARGET_MOUNTPOINT!r}, got {target!r}",
        )


def _partition_by_role(layout: Layout, role: str) -> dict[str, Any]:
    matches = [partition for partition in layout.partitions if partition.get("role") == role]
    if len(matches) != 1:
        raise Refused(
            "layout.role-count",
            f"layout must contain exactly one {role!r} partition; found {len(matches)}",
        )
    return matches[0]


def device_for(disk: str, number: int) -> str:
    """Name an allow-listed whole-disk partition node without guessing paths.

    /dev/sda + 1 is /dev/sda1, while /dev/nvme0n1 + 1 is /dev/nvme0n1p1.
    """
    if not DEVICE_PATH.fullmatch(disk):
        raise Refused("disk.path", f"{disk!r} is not an allow-listed whole block device")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise Refused("partition.number", f"partition number must be a positive integer, got {number!r}")
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

    The sequence starts by writing the GPT commands returned by Layout.commands.
    They are explicitly destructive and are not interchangeable with partprobe:
    partprobe only asks the kernel to re-read a partition table that already
    exists; it does not create that table.
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
    for index, command in enumerate(layout.commands()):
        if not command or command[0] != "sgdisk" or command[-1] != layout.disk:
            raise Refused("layout.command", "partition layout contains an unexpected disk command")
        purpose = (
            "erase the existing partition table before creating the requested GPT layout"
            if index == 0 and "--zap-all" in command
            else "create or define a partition in the requested GPT layout"
        )
        steps.append(Step(command, purpose, destructive=True))

    steps.extend([
        Step(
            ["partprobe", layout.disk],
            "ask the kernel to re-read the newly written partition table",
        ),
        Step(
            ["udevadm", "settle"],
            "wait for partition device nodes to appear before formatting",
        ),
        Step(
            [FILESYSTEMS[filesystem]["mkfs"], *FILESYSTEMS[filesystem]["args"], root_device],
            f"create {filesystem} on the root partition",
            destructive=True,
        ),
    ])

    if esp_device is not None:
        steps.append(
            Step(
                ["mkfs.fat", "-F", "32", esp_device],
                "format the EFI system partition as FAT32",
                destructive=True,
            )
        )

    steps.append(
        Step(["mount", root_device, TARGET_MOUNTPOINT], "mount the root filesystem in the fixed target")
    )

    if esp_device is not None:
        steps.extend([
            Step(
                ["mkdir", "-p", f"{TARGET_MOUNTPOINT}/boot/efi"],
                "create the ESP mount point inside the target tree",
            ),
            Step(
                ["mount", esp_device, f"{TARGET_MOUNTPOINT}/boot/efi"],
                "mount the ESP inside the target tree, not on the live system",
            ),
        ])

    return steps


def backend_command(
    layout: Layout,
    system_file: str = SYSTEM_CONFIG_PATH,
    target: str = TARGET_MOUNTPOINT,
) -> list[str]:
    """Return only the pinned Guix handoff argv; never run it.

    The source file, channel lock and target are fixed by INSTALLER-HANDOFF.md.
    A caller cannot substitute an arbitrary Scheme file or mount root.
    """
    _validate_layout_confirmation(layout)
    _validate_target(target)
    if system_file != SYSTEM_CONFIG_PATH:
        raise Refused(
            "backend.system-file",
            f"system configuration path must be exactly {SYSTEM_CONFIG_PATH!r}",
        )
    return list(build_argv(SYSTEM_CONFIG_PATH, TARGET_MOUNTPOINT))


def render(steps: list[Step], command: list[str]) -> str:
    """Render argv for review only; output explicitly states that it is not run."""
    lines = ["# NOT EXECUTED - review every line; destructive steps erase data", ""]
    for step in steps:
        marker = "DESTRUCTIVE" if step.destructive else "safe"
        lines.append(f"# [{marker}] {step.purpose}")
        lines.append(shlex.join(step.command))
        lines.append("")
    lines.append("# pinned Guix handoff (not executed)")
    lines.append(shlex.join(command))
    return "\n".join(lines) + "\n"
