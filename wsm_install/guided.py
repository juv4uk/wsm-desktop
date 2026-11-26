# SPDX-License-Identifier: LicenseRef-Volnist
"""A guided install flow for a console, not a GUI.

The minimal live image has no desktop, so the installer must be usable by
someone who does not know the exact command line. This module is that flow: it
lists candidate disks, shows what the hardware report already knows, and asks
for the one confirmation that matters - typing the disk name.

Design rules, all of them consequences of the rest of the repository:

* **the user picks the disk, never the tool.** There is no "auto" mode; a
  recommendation would be a guess with a filesystem on the end of it;
* **the confirmation is the disk name typed again**, not a yes/no. A "y" is
  pressed on autopilot; `/dev/nvme0n1` is not;
* **every question has a default that changes nothing.** Enter means "stop", not
  "proceed";
* **input and output are injected**, so the whole flow is testable without a
  terminal, a disk or root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol


class Console(Protocol):
    def write(self, text: str) -> None: ...
    def read(self, prompt: str) -> str: ...


@dataclass
class Candidate:
    path: str
    size_bytes: int
    removable: bool

    def human_size(self) -> str:
        gib = self.size_bytes / (1024 ** 3)
        return f"{gib:.0f} GiB" if gib >= 1 else f"{self.size_bytes / (1024 ** 2):.0f} MiB"


def list_disks(sys_block: Path) -> list[Candidate]:
    """Read whole disks from sysfs. Loop and ram devices are not install targets."""
    found: list[Candidate] = []
    if not sys_block.is_dir():
        return found
    for entry in sorted(sys_block.iterdir()):
        name = entry.name
        if name.startswith(("loop", "ram", "zram", "sr", "dm-", "md")):
            continue
        size_path = entry / "size"
        if not size_path.is_file():
            continue
        try:
            # /sys/block/<dev>/size is in 512-byte sectors.
            sectors = int(size_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        removable = (entry / "removable").is_file() and (
            (entry / "removable").read_text(encoding="utf-8").strip() == "1"
        )
        found.append(Candidate(f"/dev/{name}", sectors * 512, removable))
    return found


def _ask(console: Console, prompt: str, default: str = "") -> str:
    answer = console.read(prompt).strip()
    return answer if answer else default


def run_guided(
    console: Console,
    candidates: Iterable[Candidate],
    preview: Callable[[str, int, str], object],
    evidence_note: str = "",
) -> int:
    """Choose a target and show a read-only preview; real APPLY is disabled."""
    disks = list(candidates)
    console.write("WSM install preview\n\n")

    if evidence_note:
        console.write(f"Hardware: {evidence_note}\n\n")

    if not disks:
        console.write(
            "No whole disks were found. No installation can be planned.\n"
            "If the disk is attached, check that the kernel sees it: lsblk\n"
        )
        return 1

    console.write("Disks available for preview:\n")
    for index, disk in enumerate(disks, start=1):
        removable = " (removable)" if disk.removable else ""
        console.write(f"  {index}) {disk.path}  {disk.human_size()}{removable}\n")
    console.write("\n")

    choice = _ask(console, "Choose a disk by number, or press Enter to stop: ")
    if not choice:
        console.write("Stopped. Nothing was changed.\n")
        return 1
    if not choice.isdigit() or not (1 <= int(choice) <= len(disks)):
        console.write("That is not one of the listed numbers. Stopped. Nothing was changed.\n")
        return 1

    disk = disks[int(choice) - 1]
    firmware = _ask(console, "Firmware [uefi/bios] (default uefi): ", "uefi").lower()
    if firmware not in {"uefi", "bios"}:
        console.write("Unknown firmware. Stopped. Nothing was changed.\n")
        return 1

    console.write("\n")
    console.write(
        f"Preview target: {disk.path} ({disk.human_size()}). "
        "No disk will be changed.\n"
    )
    typed = console.read("Type the disk path to confirm this preview, or press Enter to stop: ").strip()
    if typed != disk.path:
        console.write("Confirmation does not match. Stopped. Nothing was changed.\n")
        return 1

    console.write("\nPreparing a read-only preview...\n")
    result = preview(disk.path, disk.size_bytes, firmware)
    if isinstance(result, int) and result != 0:
        console.write(
            f"Preview could not be generated (exit {result}). "
            "APPLY is disabled; nothing was changed.\n"
        )
        return result

    console.write(
        "Preview complete. APPLY is disabled; no disk commands were executed "
        "and WSM was NOT installed.\n"
    )
    return 0
