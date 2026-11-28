# SPDX-License-Identifier: LicenseRef-Volnist
"""Turn a partition layout into an ordered list of steps. Emit, never run.

`partition.py` answers "what should the disk look like". This module answers the
next question: what has to happen, in what order, to get from that layout to a
mounted target that `guix system init` can write into.

Everything here is data. No function opens a device, formats anything or mounts
anything. The caller decides, one step at a time.

The ordering matters and is the whole point:

1. replace the existing partition table and create the selected GPT entries;
2. re-read the partition table - the kernel does not always notice new
   partitions on its own, and formatting a stale device node formats the wrong
   thing;
3. format the ESP and the root;
4. mount root, then the ESP *inside* it - a bootloader installed into an ESP
   that is not part of the target tree lands on the live system;
5. only then hand the target to the backend.

The first supported Guix target, systems/desktop.scm, declares an ext4 root.
Until WSM has a reviewed generator that changes the Guix declaration together
with the planned formatter, this module deliberately accepts only ext4.
btrfs and xfs remain future capabilities, not options in the current preview.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wsm_install.partition import Layout, Refused

# Privileged tools are identified by exact executable basename. Guix System
# does not promise FHS /usr/bin or /usr/sbin paths; resolving through inherited
# PATH would be unsafe because the eventual caller is privileged.
TRUSTED_PROFILE_ROOT = Path("/run/current-system/profile")
TRUSTED_TOOLS = {
    "sgdisk": "sgdisk",
    "partprobe": "partprobe",
    "udevadm": "udevadm",
    "mkfs.ext4": "mkfs.ext4",
    "mkfs.fat": "mkfs.fat",
    "mount": "mount",
    "mkdir": "mkdir",
}


class TrustedToolResolutionError(RuntimeError):
    """A required privileged executable is absent or ambiguous in Guix profile."""


def resolve_trusted_tool(
    name: str,
    *,
    profile_root: Path | str = TRUSTED_PROFILE_ROOT,
) -> str:
    """Resolve one allowlisted executable only inside the active Guix system profile.

    Both profile directories are checked because Guix packages may expose
    administrative utilities in either bin or sbin. Zero or multiple
    executable matches fail closed. No inherited PATH or host FHS fallback is
    consulted.
    """
    if not isinstance(name, str) or name not in TRUSTED_TOOLS:
        raise TrustedToolResolutionError(f"tool is not allowlisted: {name!r}")

    root = Path(profile_root)
    if not root.is_absolute():
        raise TrustedToolResolutionError(
            f"Guix system profile root must be absolute: {str(root)!r}"
        )

    basename = TRUSTED_TOOLS[name]
    matches: list[Path] = []
    for directory in ("bin", "sbin"):
        candidate = root / directory / basename
        try:
            executable = candidate.is_file() and os.access(candidate, os.X_OK)
        except OSError:
            executable = False
        if executable:
            matches.append(candidate)

    if len(matches) != 1:
        raise TrustedToolResolutionError(
            f"expected exactly one executable for {name!r} under "
            f"{str(root)!r}/bin or sbin; found {len(matches)}"
        )
    return str(matches[0])


ROOT_FILESYSTEM = "ext4"
FILESYSTEMS = {
    ROOT_FILESYSTEM: {"mkfs": "mkfs.ext4", "args": ["-F"], "root": True},
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
    *,
    profile_root: Path | str = TRUSTED_PROFILE_ROOT,
) -> list[Step]:
    """Build the ordered step list for a layout, or refuse."""
    # A Layout can be passed between modules or reconstructed by another caller.
    # Re-check that exact-disk consent and observed size survived that handoff.
    layout.validate_confirmation()
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

    # Resolve the complete privileged tool allowlist before returning any plan.
    # Missing or ambiguous executables must prevent a misleading install preview.
    resolved_tools = {
        name: resolve_trusted_tool(name, profile_root=profile_root)
        for name in TRUSTED_TOOLS
    }

    root = _partition_by_role(layout, "root")
    esp = None
    if layout.firmware == "uefi":
        esp = _partition_by_role(layout, "esp")

    root_device = device_for(layout.disk, root["number"])

    # Partition-table writes are part of the plan, not an implicit precondition.
    # Keep the planner argv, but bind the executable to the absolute-path policy.
    # This is still preview data; it does not authorize APPLY.
    partition_table_steps: list[Step] = []
    for index, command in enumerate(layout.commands()):
        if not command or command[0] != "sgdisk":
            raise Refused(
                "partition.command",
                "layout planner returned an unknown partition-table executable",
            )
        if index == 0:
            purpose = (
                "replace the existing partition table before creating the selected GPT layout; "
                "all previous partition entries are destroyed"
            )
        else:
            partition = layout.partitions[index - 1]
            purpose = (
                f"create GPT partition {partition['number']} "
                f"({partition['name']}, role {partition['role']})"
            )
        partition_table_steps.append(
            Step(
                [resolved_tools["sgdisk"], *command[1:]],
                purpose,
                destructive=True,
            )
        )

    steps: list[Step] = partition_table_steps + [
        Step(
            [resolved_tools["partprobe"], layout.disk],
            "re-read the partition table; the kernel does not always notice new partitions",
        ),
        Step(
            [resolved_tools["udevadm"], "settle"],
            "wait for device nodes to appear before touching them",
        ),
        Step(
            [resolved_tools[FILESYSTEMS[filesystem]["mkfs"]],
             *FILESYSTEMS[filesystem]["args"], root_device],
            f"create {filesystem} on the root partition",
            destructive=True,
        ),
    ]

    if esp is not None:
        esp_device = device_for(layout.disk, esp["number"])
        steps.append(
            Step(
                [resolved_tools["mkfs.fat"], "-F", "32", esp_device],
                "format the EFI system partition as FAT32; UEFI firmware reads nothing else",
                destructive=True,
            )
        )

    steps.append(
        Step([resolved_tools["mount"], root_device, target], f"mount the root filesystem at {target}")
    )

    if esp is not None:
        steps.append(
            Step(
                [resolved_tools["mkdir"], "-p", f"{target}/boot/efi"],
                "create the ESP mount point inside the target",
            )
        )
        steps.append(
            Step(
                [resolved_tools["mount"], device_for(layout.disk, esp["number"]),
                 f"{target}/boot/efi"],
                "mount the ESP inside the target tree; outside it the bootloader lands on the live system",
            )
        )

    return steps


def backend_command(layout: Layout, system_file: str, target: str = "/mnt") -> list[str]:
    """The handoff command. This module does not run it, and neither should a UI."""
    layout.validate_confirmation()
    if not system_file.endswith(".scm"):
        raise Refused(
            "backend.system-file",
            f"expected a .scm system file, got {system_file!r}",
        )
    # guix lives in a profile path that differs per system, so it is the one
    # command allowed to be resolved by the caller - and the caller runs it
    # interactively, not from a root shell.
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
