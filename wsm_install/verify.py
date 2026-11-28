# SPDX-License-Identifier: LicenseRef-Volnist
"""Postconditions for allowlisted install steps; an unknown step fails closed.

#280 acceptance criterion 5: every allowlisted step has a real, checkable
postcondition, and an unknown step is always `unverified`. The prototype that
motivated the issue reported success for `partprobe`, `udevadm` and for anything it
did not recognise, which is the worst possible default on a disk-writing path.

This module is deliberately pure. It never runs a command and never resolves a
PATH: it asks an injected observer for read-only facts and decides. That keeps the
contract testable with fakes, keeps the PATH-hijack class out of verification, and
means the same code serves the preview today and a future APPLY path without
changing its meaning.

Three outcomes, and the default is the third:

    verified    the observed state matches the step's postcondition
    failed      the observation contradicts it — do not continue
    unverified  nobody could prove it: unknown tool, unreadable state, no verifier

`unverified` is not a warning. `wsm_install.journal` already stops on it, which is
why the distinction is kept here rather than collapsed into a boolean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from wsm_install.install_steps import TRUSTED_TOOLS, Step


@dataclass(frozen=True)
class Verification:
    status: str
    detail: str


class Observer(Protocol):
    """Read-only facts a verifier may consult. Implementations own the tool paths."""

    def filesystem_of(self, path: str) -> str | None: ...

    def is_mounted(self, path: str) -> bool: ...

    def partitioned_disks(self) -> Sequence[str]: ...

    def path_exists(self, path: str) -> bool: ...


_DEVICE = re.compile(r"/dev/[A-Za-z0-9._/-]+")

# What a formatted partition must report, keyed by the mkfs executable.
_MKFS_EXPECTED = {
    TRUSTED_TOOLS["mkfs.ext4"]: "ext4",
    TRUSTED_TOOLS["mkfs.fat"]: "vfat",
}


def _unverified(reason: str) -> Verification:
    return Verification("unverified", reason)


def _device_argument(step: Step) -> str | None:
    for argument in reversed(step.command[1:]):
        match = _DEVICE.fullmatch(argument)
        if match:
            return argument
    return None


def _verify_partition_table(step: Step, observer: Observer) -> Verification:
    disk = _device_argument(step)
    if disk is None:
        return _unverified("the partition-table step names no device; nothing to verify")
    disks = tuple(observer.partitioned_disks())
    if disk in disks:
        return Verification("verified", f"{disk} is present in the observed partition-table set")
    return Verification("failed", f"{disk} is absent; observed disks: {', '.join(disks) or 'none'}")


def _verify_mkfs(step: Step, observer: Observer) -> Verification:
    expected = _MKFS_EXPECTED.get(step.command[0])
    if expected is None:
        return _unverified(f"no expected filesystem is known for {step.command[0]!r}")
    device = _device_argument(step)
    if device is None:
        return _unverified("the mkfs step names no device; nothing to verify")
    observed = observer.filesystem_of(device)
    if observed is None:
        return _unverified(f"{device} reports no filesystem; the postcondition cannot be read")
    if observed == expected:
        return Verification("verified", f"{device} reports {observed}")
    return Verification("failed", f"{device} reports {observed}, expected {expected}")


def _verify_mount(step: Step, observer: Observer) -> Verification:
    if len(step.command) < 3:
        return _unverified("the mount step does not name a mountpoint")
    mountpoint = step.command[-1]
    if observer.is_mounted(mountpoint):
        return Verification("verified", f"{mountpoint} is mounted")
    return Verification("failed", f"{mountpoint} is not mounted")


def _verify_mkdir(step: Step, observer: Observer) -> Verification:
    if len(step.command) < 2:
        return _unverified("the mkdir step names no path")
    path = step.command[-1]
    if observer.path_exists(path):
        return Verification("verified", f"{path} exists")
    return Verification("failed", f"{path} does not exist")


def _verify_partprobe(step: Step, observer: Observer) -> Verification:
    # partprobe has no postcondition of its own: the kernel either exposes the new
    # table or it does not, and that is what the partition-table verifier reads.
    # Claiming success here is exactly the defect #280 describes.
    return _unverified(
        "partprobe has no observable postcondition; the partition-table step carries the check"
    )


def _verify_udevadm(step: Step, observer: Observer) -> Verification:
    # "settle" waits; it does not leave a state of its own. The device node is
    # verified by the step that uses the node, not by the wait.
    return _unverified(
        "udevadm settle leaves no state to check; the consuming step verifies its device"
    )


VERIFIERS: dict[str, Callable[[Step, Observer], Verification]] = {
    TRUSTED_TOOLS["sgdisk"]: _verify_partition_table,
    TRUSTED_TOOLS["partprobe"]: _verify_partprobe,
    TRUSTED_TOOLS["udevadm"]: _verify_udevadm,
    TRUSTED_TOOLS["mkfs.ext4"]: _verify_mkfs,
    TRUSTED_TOOLS["mkfs.fat"]: _verify_mkfs,
    TRUSTED_TOOLS["mount"]: _verify_mount,
    TRUSTED_TOOLS["mkdir"]: _verify_mkdir,
}


def verify_step(step: Step, observer: Observer) -> Verification:
    """Return the postcondition verdict for one step. Unknown tools fail closed."""
    executable = step.command[0] if step.command else ""
    verifier = VERIFIERS.get(executable)
    if verifier is None:
        return _unverified(
            f"no postcondition is defined for {executable!r}; refusing to call it verified"
        )
    try:
        return verifier(step, observer)
    except OSError as exc:
        return _unverified(f"observation failed: {exc}")
