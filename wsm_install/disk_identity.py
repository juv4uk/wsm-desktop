# SPDX-License-Identifier: LicenseRef-Volnist
"""Disk identity, re-identified immediately before the destructive phase.

#280 criterion 3: before the first write, the executor checks that the target is
still the device it planned against — major/minor, size, removable flag, partition
topology — and refuses on any drift. The prototype checked `acknowledgement == disk`
once, long before the loop; between planning and writing, a device can be replugged,
a different disk can take the same name, or the live medium itself can be named.

The identity is a frozen record and the comparison is pure. Facts arrive through an
injected observer, so nothing here runs a command, resolves a PATH or touches
`/sys` by itself, and the whole contract is testable with fakes.

Two refusals are worth keeping apart for the operator:

    identity.drift          the device changed since planning
    identity.live-device    the target is the medium the installer booted from

The second is not drift — it is the classic way to destroy the running system, and
a message that says "size changed" would be actively misleading there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class IdentityError(Exception):
    """A refusal with a stable code, like the rest of the installer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class DiskObserver(Protocol):
    """Read-only facts about block devices. Implementations own the tool paths."""

    def block_identity(self, path: str) -> dict[str, object] | None: ...

    def partitions(self, path: str) -> Sequence[str]: ...

    def live_device(self) -> str | None: ...


@dataclass(frozen=True)
class DiskIdentity:
    """What the target looked like when it was planned against."""

    path: str
    major_minor: str
    size_bytes: int
    removable: bool
    partitions: tuple[str, ...]


def capture(observer: DiskObserver, path: str) -> DiskIdentity:
    """Record the identity of the target disk, or refuse if it cannot be read."""
    facts = observer.block_identity(path)
    if not isinstance(facts, dict):
        raise IdentityError("identity.missing", f"{path} is not a readable block device")

    major_minor = facts.get("major_minor")
    size_bytes = facts.get("size_bytes")
    removable = facts.get("removable")

    if not isinstance(major_minor, str) or not major_minor:
        raise IdentityError("identity.missing", f"{path} reports no major:minor")
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        raise IdentityError("identity.missing", f"{path} reports no usable size")
    if not isinstance(removable, bool):
        raise IdentityError("identity.missing", f"{path} reports no removable flag")

    return DiskIdentity(
        path=path,
        major_minor=major_minor,
        size_bytes=size_bytes,
        removable=removable,
        partitions=tuple(observer.partitions(path)),
    )


def require_unchanged(expected: DiskIdentity, observer: DiskObserver) -> None:
    """Re-identify the target and refuse on any drift, before the first write."""
    live = observer.live_device()
    if isinstance(live, str) and live and _same_device(live, expected.path):
        raise IdentityError(
            "identity.live-device",
            f"{expected.path} is the medium this system booted from",
        )

    actual = capture(observer, expected.path)

    if actual.major_minor != expected.major_minor:
        raise IdentityError(
            "identity.drift",
            f"{expected.path} moved from {expected.major_minor} to {actual.major_minor}; "
            "a different device may now hold this name",
        )
    if actual.size_bytes != expected.size_bytes:
        raise IdentityError(
            "identity.drift",
            f"{expected.path} changed size from {expected.size_bytes} to {actual.size_bytes}",
        )
    if actual.removable != expected.removable:
        raise IdentityError(
            "identity.drift",
            f"{expected.path} removable flag changed from {expected.removable} to {actual.removable}",
        )
    if actual.partitions != expected.partitions:
        raise IdentityError(
            "identity.drift",
            f"{expected.path} topology changed: {expected.partitions} -> {actual.partitions}",
        )


def _same_device(left: str, right: str) -> bool:
    """Compare a device path with a live-medium path, ignoring a partition suffix.

    The live medium is usually reported as the partition that holds the squashfs
    (`/dev/sdb1`) while the target is the whole disk (`/dev/sdb`), so comparing the
    strings verbatim would miss exactly the case this check exists for.
    """
    if left == right:
        return True
    for whole, candidate in ((right, left), (left, right)):
        if candidate.startswith(whole) and candidate[len(whole):].isdigit():
            return True
        if candidate.startswith(whole + "p") and candidate[len(whole) + 1:].isdigit():
            return True
    return False
