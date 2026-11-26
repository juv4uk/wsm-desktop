# SPDX-License-Identifier: LicenseRef-Volnist
"""A pseudo-graphical installer for machines that have a screen but no desktop.

Three frontends, one backend:

* console (`--guided`) - a read-only target selector;
* pseudo-graphics (`--tui`) - a full-screen read-only preview;
* Calamares - an optional GUI shell with the same disabled-APPLY contract.

Why not curses: `curses` is in the standard library but drags terminal
capability handling and a global screen state that is painful to test and
breaks on serial consoles. The screen here is a list of lines plus a key
reader, both injectable, so the whole flow is testable without a terminal.

Why not a real GUI at this level: the point of the middle tier is to work on a
machine with 1-2 GiB of RAM and no GPU. Box drawing characters cost nothing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from wsm_install.guided import Candidate

BOX_WIDTH = 62
CLEAR = "\x1b[2J\x1b[H"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"


class Screen(Protocol):
    def render(self, lines: list[str]) -> None: ...
    def read_key(self) -> str: ...


@dataclass
class TerminalScreen:
    """Real terminal: ANSI for drawing, raw single keys for input."""

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
                # Arrow keys arrive as ESC [ A/B/C/D.
                rest = sys.stdin.read(2)
                return {"[A": "up", "[B": "down"}.get(rest, "esc")
            return {"\r": "enter", "\n": "enter", "q": "quit", "j": "down", "k": "up"}.get(
                char, char
            )
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def box(title: str, body: list[str], width: int = BOX_WIDTH) -> list[str]:
    """Draw a box. Pure function, so the layout is testable without a terminal."""
    inner = max(width - 4, 10)
    lines = ["┌" + "─" * (width - 2) + "┐"]
    lines.append("│ " + title[: inner].ljust(inner) + " │")
    lines.append("├" + "─" * (width - 2) + "┤")
    for entry in body:
        lines.append("│ " + entry[: inner].ljust(inner) + " │")
    lines.append("└" + "─" * (width - 2) + "┘")
    return lines


def disk_list(candidates: list[Candidate], selected: int) -> list[str]:
    lines: list[str] = []
    for index, disk in enumerate(candidates):
        marker = ">" if index == selected else " "
        removable = "  removable" if disk.removable else ""
        lines.append(f"{marker} {index + 1}. {disk.path:<16} {disk.human_size():>9}{removable}")
    return lines


def run_tui(
    screen: Screen,
    candidates: Iterable[Candidate],
    preview: Callable[[str, int, str], object],
    evidence_note: str = "",
) -> int:
    """Choose a target with arrow keys and render a preview; never install."""
    disks = list(candidates)

    if not disks:
        screen.render(box("WSM install", [
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
        screen.render(box("WSM install", body))

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
            f"Disk: {disk.path}  ({disk.human_size()})",
            "",
            f"  [1] UEFI{'  <-' if firmware == 'uefi' else ''}",
            f"  [2] BIOS{'  <-' if firmware == 'bios' else ''}",
            "",
            "1/2 or arrows to change, Enter to continue, q to quit.",
        ]))
        key = screen.read_key()
        if key == "quit":
            return 1
        if key in {"1"}:
            firmware = "uefi"
        elif key in {"2"}:
            firmware = "bios"
        elif key == "up":
            firmware = "uefi"
        elif key == "down":
            firmware = "bios"
        elif key == "enter":
            break

    typed = ""
    while True:
        screen.render(box("Confirm", [
            "",
            f"Preview target: {disk.path} ({disk.human_size()}).",
            "",
            "No disk will be changed. Type the path to confirm this preview, or q to quit.",
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
            "The path you typed does not match the chosen disk.",
            "Nothing was changed.",
        ]))
        screen.read_key()
        return 1

    screen.render(box("Preview", ["", f"Preparing a read-only preview for {disk.path}..."]))
    result = preview(disk.path, disk.size_bytes, firmware)
    if isinstance(result, int) and result != 0:
        screen.render(box("Preview failed", [
            "",
            f"Preview could not be generated (exit {result}).",
            "APPLY is disabled. Nothing was changed.",
        ]))
        return result

    screen.render(box("Preview complete", [
        "",
        f"Plan prepared for {disk.path} ({firmware}).",
        "",
        "APPLY is disabled.",
        "No disk commands were executed.",
        "WSM was NOT installed.",
    ]))
    return 0
