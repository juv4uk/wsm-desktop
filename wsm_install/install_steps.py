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

from dataclasses import dataclass
from typing import Any

from wsm_install.partition import Layout, Refused

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


def _partition_by_role(layout: Layout, role: str) -> dict[str, Any]:
    for partition in layout.partitions:
        if partition["role"] == role:
            return partition
    raise Refused("layout.role-missing", f"layout has no partition with role {role!r}")


def device_for(disk: str, number: int) -> str:
    """Name the partition device the way the kernel does.

    /dev/sda + 1 is /dev/sda1, but /dev/nvme0n1 + 1 is /dev/nvme0n1p1. Getting
    this wrong formats the disk instead of the partition, so it is computed in
    one place and tested.
    """
    if disk[-1].isdigit():
        return f"{disk}p{number}"
    return f"{disk}{number}"


def plan_steps(
    layout: Layout,
    filesystem: str = "ext4",
    target: str = "/mnt",
    hostname: str | None = None,
) -> list[Step]:
    """Build the ordered step list for a layout, or refuse."""
    if filesystem not in FILESYSTEMS:
        raise Refused(
            "filesystem.unsupported",
            f"{filesystem!r} is not supported; choose one of {sorted(FILESYSTEMS)}",
        )
    if not target.startswith("/") or target == "/":
        raise Refused(
            "target.unsafe",
            f"target must be an absolute mount point below /, got {target!r}",
        )

    root = _partition_by_role(layout, "root")
    esp = None
    if layout.firmware == "uefi":
        esp = _partition_by_role(layout, "esp")

    root_device = device_for(layout.disk, root["number"])
    steps: list[Step] = [
        Step(
            ["partprobe", layout.disk],
            "re-read the partition table; the kernel does not always notice new partitions",
        ),
        Step(
            ["udevadm", "settle"],
            "wait for device nodes to appear before touching them",
        ),
        Step(
            [FILESYSTEMS[filesystem]["mkfs"], *FILESYSTEMS[filesystem]["args"], root_device],
            f"create {filesystem} on the root partition",
            destructive=True,
        ),
    ]

    if esp is not None:
        esp_device = device_for(layout.disk, esp["number"])
        steps.append(
            Step(
                ["mkfs.fat", "-F", "32", esp_device],
                "format the EFI system partition as FAT32; UEFI firmware reads nothing else",
                destructive=True,
            )
        )

    steps.append(
        Step(["mount", root_device, target], f"mount the root filesystem at {target}")
    )

    if esp is not None:
        steps.append(
            Step(
                ["mkdir", "-p", f"{target}/boot/efi"],
                "create the ESP mount point inside the target",
            )
        )
        steps.append(
            Step(
                ["mount", device_for(layout.disk, esp["number"]), f"{target}/boot/efi"],
                "mount the ESP inside the target tree; outside it the bootloader lands on the live system",
            )
        )

    return steps


def backend_command(layout: Layout, system_file: str, target: str = "/mnt") -> list[str]:
    """The handoff command. This module does not run it, and neither should a UI."""
    if not system_file.endswith(".scm"):
        raise Refused(
            "backend.system-file",
            f"expected a .scm system file, got {system_file!r}",
        )
    return ["guix", "system", "init", system_file, target]


def render(steps: list[Step], command: list[str]) -> str:
    lines = ["# NOT EXECUTED - review every line before running anything", ""]
    for step in steps:
        marker = "DESTRUCTIVE" if step.destructive else "safe"
        lines.append(f"# [{marker}] {step.purpose}")
        lines.append(" ".join(step.command))
        lines.append("")
    lines.append("# handoff to the backend")
    lines.append(" ".join(command))
    return "\n".join(lines) + "\n"
