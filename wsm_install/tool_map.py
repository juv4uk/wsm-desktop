# SPDX-License-Identifier: LicenseRef-Volnist
"""One authoritative map from a logical tool to the executable and its Guix package.

#645 opens with a divergence that already existed in the tree: `TRUSTED_TOOLS` in
`install_steps` listed seven tools including `sgdisk`, while `agent.ALLOWED_PROGRAMS`
listed six and did not include it. The planner could therefore emit a step the
agent's own validator would refuse. Two lists, one truth, and the truth was whichever
module you happened to read.

Every consumer now derives from this map — the planner, the agent's allowlist, the
executor's argv policy, the verifier dispatch and the preflight check. A new tool is
added here once.

`package` is the Guix package that owns the executable. It is the answer to "why is
this path allowed to exist in the image", and it is what a closure check has to
verify against. It is deliberately a package name rather than a store path: a store
path changes with every rebuild, and pinning one would tie the installer to a single
build.
"""

from __future__ import annotations

from typing import Mapping

TOOLS: Mapping[str, Mapping[str, str]] = {
    "sgdisk": {"executable": "/usr/sbin/sgdisk", "package": "gptfdisk"},
    "partprobe": {"executable": "/usr/sbin/partprobe", "package": "parted"},
    "udevadm": {"executable": "/usr/bin/udevadm", "package": "eudev"},
    "mkfs.ext4": {"executable": "/usr/sbin/mkfs.ext4", "package": "e2fsprogs"},
    "mkfs.fat": {"executable": "/usr/sbin/mkfs.fat", "package": "dosfstools"},
    "mount": {"executable": "/usr/bin/mount", "package": "util-linux"},
    "mkdir": {"executable": "/usr/bin/mkdir", "package": "coreutils"},
}

EXECUTABLES = frozenset(spec["executable"] for spec in TOOLS.values())
BASENAMES = frozenset(executable.rsplit("/", 1)[-1] for executable in EXECUTABLES)


def executable(name: str) -> str:
    """The absolute executable for a logical tool name."""
    return TOOLS[name]["executable"]


def package(name: str) -> str:
    """The Guix package that owns this tool's executable."""
    return TOOLS[name]["package"]


def name_for(path: str) -> str | None:
    """Reverse lookup by FHS path or by basename under an explicit Guix prefix."""
    basename = path.rsplit("/", 1)[-1]
    for name, spec in TOOLS.items():
        if spec["executable"] == path or spec["executable"].rsplit("/", 1)[-1] == basename:
            return name
    return None
