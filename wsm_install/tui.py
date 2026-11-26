# SPDX-License-Identifier: LicenseRef-Volnist
"""A dependency-free, preview-only keyboard interface for the WSM installer."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from wsm_install.guided import Candidate

BOX_WIDTH = 62
CLEAR = "\x1b[2J\x1b[H"


class Screen(Protocol):
    def render(self, lines: list[str]) -> None: ...
    def read_key(self) -> str: ...


@dataclass(frozen=True)
class PreviewOutcome:
    """Structured result from the read-only CLI planner."""

    exit_code: int
    details: tuple[str, ...] = ()


@dataclass
class TerminalScreen:
    """Minimal POSIX terminal adapter; all drawing/input stays injectable."""

    stream: object = sys.stdout

    def render(self, lines: list[str]) -> None:
        self.stream.write(CLEAR + "\n".join(lines) + "\n")
        self.stream.flush()

    def read_key(self) -> str:
        try:
            import termios
            import tty
        except ImportError:  # pragma: no cover - non-POSIX
            return sys.stdin.readline().strip()[:1] or "q"

        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setraw(descriptor)
            char = sys.stdin.read(1)
            if char == "\x1b":
                rest = sys.stdin.read(2)
                return {"[A": "up", "[B": "down"}.get(rest, "esc")
            return {"\r": "enter", "\n": "enter", "q": "quit", "j": "down", "k": "up"}.get(char, char)
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def box(title: str, body: list[str], width: int = BOX_WIDTH) -> list[str]:
    inner = max(width - 4, 10)
    lines = ["┌" + "─" * (width - 2) + "┐"]
    lines.append("│ " + title[:inner].ljust(inner) + " │")
    lines.append("├" + "─" * (width - 2) + "┤")
    for entry in body:
        lines.append("│ " + entry[:inner].ljust(inner) + " │")
    lines.append("└" + "─" * (width - 2) + "┘")
    return lines


def disk_list(candidates: list[Candidate], selected: int) -> list[str]:
    result: list[str] = []
    for index, disk in enumerate(candidates):
        marker = ">" if index == selected else " "
        removable = "  removable" if disk.removable else ""
        result.append(f"{marker} {index + 1}. {disk.path:<16} {disk.human_size():>9}{removable}")
    return result


def run_tui(
    screen: Screen,
    candidates: Iterable[Candidate],
    preview: Callable[[str, int, str], object],
    evidence_note: str = "",
) -> int:
    """Choose a disk and display a read-only plan. There is no APPLY callback."""
    disks = list(candidates)

    if not disks:
        screen.render(box("WSM preview", [
            "No whole disks were found.",
            "If the disk is attached, check that the kernel sees it: lsblk",
            "",
            "Press q to quit.",
        ]))
        screen.read_key()
        return 1

    selected = 0
    while True:
        body = ["", "Choose a disk to preview:", ""]
        body += disk_list(disks, selected)
        body += ["", "↑/↓ or j/k to move, Enter to choose, q to quit."]
        if evidence_note:
            body += ["", f"Hardware: {evidence_note}"[: BOX_WIDTH - 4]]
        screen.render(box("WSM preview", body))
        key = screen.read_key()
        if key == "quit":
            return 1
        if key == "up":
            selected = (selected - 1) % len(disks)
        elif key == "down":
            selected = (selected + 1) % len(disks)
        elif key == "enter":
            break

    disk = disks[selected]
    firmware = "uefi"
    while True:
        screen.render(box("Firmware", [
            "",
            f"Preview target: {disk.path} ({disk.human_size()})",
            "",
            f"  [1] UEFI{'  <-' if firmware == 'uefi' else ''}",
            f"  [2] BIOS{'  <-' if firmware == 'bios' else ''}",
            "",
            "1/2 or arrows to change, Enter to continue, q to quit.",
        ]))
        key = screen.read_key()
        if key == "quit":
            return 1
        if key == "1":
            firmware = "uefi"
        elif key == "2":
            firmware = "bios"
        elif key == "up":
            firmware = "uefi"
        elif key == "down":
            firmware = "bios"
        elif key == "enter":
            break

    typed = ""
    while True:
        screen.render(box("Confirm preview", [
            "",
            f"Target: {disk.path} ({disk.human_size()})",
            "No disk will be erased or written.",
            "Type the disk path to confirm this preview, or q to quit.",
            "",
            f"  > {typed}_",
        ]))
        key = screen.read_key()
        if key == "quit":
            return 1
        if key == "enter":
            break
        if len(key) == 1 and key.isprintable():
            typed += key
        elif key in {"\x7f", "backspace"}:
            typed = typed[:-1]

    if typed != disk.path:
        screen.render(box("Stopped", [
            "",
            "The path does not match the selected disk.",
            "No commands were executed.",
        ]))
        screen.read_key()
        return 1

    screen.render(box("Planning", ["", f"Preparing a preview for {disk.path}..."]))
    result = preview(disk.path, disk.size_bytes, firmware)
    if isinstance(result, PreviewOutcome):
        exit_code = result.exit_code
        details = list(result.details)
    elif type(result) is int:
        exit_code = result
        details = []
    else:
        exit_code = 1
        details = ["Preview callback returned no exit code."]

    if exit_code != 0:
        detail = f"Preview failed (exit {exit_code})."
        screen.render(box("Preview failed", [
            "",
            detail,
            *details[:3],
            "APPLY is disabled. No disk commands were executed.",
        ]))
        screen.read_key()
        return exit_code

    screen.render(box("Preview only", [
        "",
        f"Preview completed for {disk.path} ({firmware}).",
        "",
        *details[:3],
        "APPLY is disabled.",
        "No disk commands were executed.",
        "The system is NOT installed.",
        "",
        "Press any key to return.",
    ]))
    screen.read_key()
    return 0
