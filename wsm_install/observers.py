# SPDX-License-Identifier: LicenseRef-Volnist
"""Real read-only observers, so the guarantees can run outside a test.

`disk_identity`, `verify` and `admission` all take their facts from an injected
observer: that is why they are testable without a GPU, a disk or a root shell. Until
now only fakes existed, so nothing outside the test suite could actually ask "has the
target moved?" or "did the format land?".

These implementations read `sysfs` and `/proc`, never `PATH`, and never run a command.
That is a deliberate limit: a `blkid` subprocess would reintroduce the tool-resolution
question this repository just spent a week removing, and reading `/sys` answers the
same questions for the cases the installer has.

Both roots are parameters. A test points them at a temporary tree, which is also how a
future image check can inspect a mounted image instead of the running system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

SECTOR_BYTES = 512


class SysfsDiskObserver:
    """`disk_identity.DiskObserver` over sysfs and /proc/mounts."""

    def __init__(self, sys_root: Path = Path("/sys"), mounts: Path = Path("/proc/mounts")) -> None:
        self.sys_root = Path(sys_root)
        self.mounts = Path(mounts)

    def _block_dir(self, path: str) -> Path | None:
        """Resolve only a canonical /dev whole-device path to its sysfs object."""
        if not isinstance(path, str) or not path.startswith("/dev/"):
            return None
        name = path[len("/dev/"):]
        if not name or "/" in name or name in {".", ".."}:
            return None

        candidate = self.sys_root / "class" / "block" / name
        if not candidate.is_dir():
            return None
        # A partition has its own top-level sysfs block object too. It is not
        # an admissible whole-disk target for disk identity capture.
        if (candidate / "partition").is_file():
            return None
        return candidate

    def block_identity(self, path: str) -> dict[str, object] | None:
        directory = self._block_dir(path)
        if directory is None:
            return None
        try:
            major_minor = (directory / "dev").read_text(encoding="utf-8").strip()
            sectors = int((directory / "size").read_text(encoding="utf-8").strip())
            removable = (directory / "removable").read_text(encoding="utf-8").strip() == "1"
        except (OSError, ValueError):
            return None
        if not major_minor:
            return None
        return {
            "major_minor": major_minor,
            "size_bytes": sectors * SECTOR_BYTES,
            "removable": removable,
        }

    def partitions(self, path: str) -> Sequence[str]:
        """Return only child block objects carrying a positive sysfs partition number."""
        directory = self._block_dir(path)
        if directory is None:
            return ()

        found: list[tuple[int, str]] = []
        try:
            entries = tuple(directory.iterdir())
        except OSError:
            return ()

        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
                marker = entry / "partition"
                if not marker.is_file():
                    continue
                number = int(marker.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            if number > 0:
                found.append((number, entry.name))

        found.sort()
        return tuple(f"/dev/{name}" for _, name in found)

    def live_device(self) -> str | None:
        """The block device backing `/`, or None when it is not a plain device.

        A live medium usually mounts a squashfs image, and the root of a Guix system
        may be an overlay: in both cases there is no single backing device to name, and
        returning a guess would be worse than returning None. The identity check treats
        None as "cannot tell", which is the honest answer.
        """
        try:
            lines = self.mounts.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        for line in lines:
            fields = line.split()
            if len(fields) < 2 or fields[1] != "/":
                continue
            source = fields[0]
            if source.startswith("/dev/"):
                return source
            return None
        return None


class FilesystemObserver:
    """`verify.Observer` over /proc/mounts and the filesystem itself.

    `filesystem_of` is deliberately unimplemented as a guess: without `blkid` there is
    no honest way to name a filesystem, and `verify` treats None as "unverified". The
    installer's mkfs postcondition therefore stays unverified until a trusted
    filesystem probe exists — which is the correct state, not a gap to paper over.
    """

    def __init__(self, mounts: Path = Path("/proc/mounts")) -> None:
        self.mounts = Path(mounts)

    def filesystem_of(self, path: str) -> str | None:
        return None

    def is_mounted(self, path: str) -> bool:
        try:
            lines = self.mounts.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return False
        for line in lines:
            fields = line.split()
            if len(fields) >= 2 and fields[1] == path:
                return True
        return False

    def partitioned_disks(self) -> Sequence[str]:
        return ()

    def path_exists(self, path: str) -> bool:
        return os.path.exists(path)
