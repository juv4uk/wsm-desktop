# SPDX-License-Identifier: LicenseRef-Volnist
"""Plan a disk layout. Emit commands. Never run them.

This module exists because partitioning is where an installer destroys data, and
it is the one part that can be built and tested without Guix or hardware.

The design is deliberately paranoid:

* the planner produces a list of commands as data. Nothing in this module
  executes anything, and there is no code path that opens a block device;
* every refusal names the reason. "Refusing" is the normal answer;
* the target disk must be identified by its reported size, not only its name -
  /dev/sda on one machine is /dev/nvme0n1 on another, and a name that no longer
  matches is how people lose the wrong disk;
* wiping requires an explicit acknowledgement that names the disk. A boolean
  "yes" is not enough: it has to be the thing you are about to erase.

Layouts:

* UEFI: 512 MiB ESP (FAT32) + rest as the root filesystem.
* BIOS: 1 MiB bios_grub + rest as root. The 1 MiB partition is not decoration:
  GRUB on GPT needs somewhere to put its core image.

No swap partition on purpose. The profile uses zram, and a swap partition on an
SSD is the classic way to make a desktop feel slower while claiming otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ESP_MIB = 512
BIOS_BOOT_MIB = 1
MIN_ROOT_MIB = 12 * 1024
SIZE_TOLERANCE = 0.02

DEVICE_PATH = re.compile(r"^/dev/(sd[a-z]+|nvme[0-9]+n[0-9]+|vd[a-z]+|mmcblk[0-9]+)$")


class Refused(Exception):
    """A refusal with a stable code, so callers can test it without string matching."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class Disk:
    """What we believe about the target disk, taken from a report, not from a probe."""

    path: str
    size_bytes: int
    is_removable: bool = False
    holds_running_system: bool = False
    has_existing_data: bool = True


@dataclass
class Layout:
    firmware: str
    disk: str
    partitions: list[dict[str, Any]] = field(default_factory=list)

    def commands(self) -> list[list[str]]:
        """sgdisk invocations as data. The caller decides whether to run them."""
        steps: list[list[str]] = [["sgdisk", "--zap-all", self.disk]]
        for partition in self.partitions:
            steps.append([
                "sgdisk",
                f"--new={partition['number']}:{partition['start']}:{partition['end']}",
                f"--typecode={partition['number']}:{partition['typecode']}",
                f"--change-name={partition['number']}:{partition['name']}",
                self.disk,
            ])
        return steps


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise Refused(code, message)


def validate_target(disk: Disk, acknowledgement: str | None, firmware: str) -> None:
    """Every reason this disk must not be touched, in the order that matters most."""
    _require(
        bool(DEVICE_PATH.match(disk.path)),
        "disk.path",
        f"{disk.path!r} is not a whole block device; partitions and images are refused",
    )
    _require(
        firmware in {"uefi", "bios"},
        "disk.firmware",
        f"firmware must be 'uefi' or 'bios', got {firmware!r}",
    )
    _require(
        not disk.holds_running_system,
        "disk.running-system",
        f"{disk.path} holds the system we are running from",
    )
    _require(
        disk.size_bytes >= (MIN_ROOT_MIB + ESP_MIB) * 1024 * 1024,
        "disk.too-small",
        f"{disk.path} is {disk.size_bytes} bytes; the smallest supported layout needs "
        f"{MIN_ROOT_MIB + ESP_MIB} MiB",
    )
    if disk.has_existing_data:
        _require(
            acknowledgement == disk.path,
            "disk.acknowledgement",
            f"{disk.path} contains data; refusing without an acknowledgement that names "
            f"exactly this disk (got {acknowledgement!r})",
        )


def plan(
    disk: Disk,
    firmware: str,
    acknowledgement: str | None = None,
    expected_size_bytes: int | None = None,
) -> Layout:
    """Build a layout, or refuse with a reason."""
    validate_target(disk, acknowledgement, firmware)

    if expected_size_bytes is not None:
        drift = abs(disk.size_bytes - expected_size_bytes) / max(expected_size_bytes, 1)
        _require(
            drift <= SIZE_TOLERANCE,
            "disk.size-drift",
            f"{disk.path} reports {disk.size_bytes} bytes but {expected_size_bytes} was "
            f"expected ({drift:.1%} drift); the disk may have been replaced",
        )

    layout = Layout(firmware=firmware, disk=disk.path)
    cursor = 1
    if firmware == "bios":
        layout.partitions.append({
            "number": 1,
            "start": f"{cursor}MiB",
            "end": f"{cursor + BIOS_BOOT_MIB}MiB",
            "typecode": "ef02",
            "name": "wsm-bios-boot",
            "role": "bios-grub",
        })
        cursor += BIOS_BOOT_MIB
    else:
        layout.partitions.append({
            "number": 1,
            "start": f"{cursor}MiB",
            "end": f"{cursor + ESP_MIB}MiB",
            "typecode": "ef00",
            "name": "wsm-esp",
            "role": "esp",
        })
        cursor += ESP_MIB

    layout.partitions.append({
        "number": len(layout.partitions) + 1,
        "start": f"{cursor}MiB",
        "end": "0",
        "typecode": "8300",
        "name": "wsm-root",
        "role": "root",
    })
    return layout


def render(layout: Layout) -> str:
    """Human-readable shell, for review only. Never executed by this module."""
    lines = [f"# {layout.disk}: {layout.firmware} layout", "# NOT EXECUTED - review first"]
    for step in layout.commands():
        lines.append(" ".join(step))
    return "\n".join(lines) + "\n"
