# SPDX-License-Identifier: LicenseRef-Volnist
"""Resolve a trusted tool to an absolute path without ever consulting PATH.

The installer's tool table names FHS paths (`/usr/sbin/sgdisk`), and a Guix live
image has no `/usr` at all: its tools live in `/run/current-system/profile/bin` and
in `/gnu/store/<hash>-<package>/bin`. Hardcoding a store hash would pin the plan to
one build, and searching `PATH` would reintroduce exactly the hijack class the
executor's allowlist exists to remove (Omarchy #8172).

So resolution takes an **explicit, ordered list of prefixes** from the caller — the
profile directories of the image being installed, not the environment of whoever
runs the code. No `os.environ`, no `shutil.which`. A tool is found only if it sits
directly in one of the prefixes it was given.

This module resolves; it does not decide admissibility. `wsm_install.executor` still
holds the allowlist, and `is_admissible_path` is the check it can adopt once the
table moves off FHS paths.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable, Sequence


@lru_cache(maxsize=1)
def trusted_basenames() -> frozenset[str]:
    """Basenames of the trusted tools.

    Imported lazily: install_steps imports resolve() from this module, so a
    module-level import here would be circular. The table is a constant, so caching
    it once is enough.
    """
    from wsm_install.install_steps import TRUSTED_TOOLS

    return frozenset(os.path.basename(path) for path in TRUSTED_TOOLS.values())

# Profile directories of a Guix system, then the FHS locations used by the host
# preview. Order matters: the first prefix that has the tool wins, so a host tool
# can never shadow the image's own.
DEFAULT_PREFIXES: tuple[str, ...] = (
    "/run/current-system/profile/bin",
    "/run/current-system/profile/sbin",
    "/usr/bin",
    "/usr/sbin",
)


def resolve(
    name: str,
    *,
    prefixes: Sequence[str] = DEFAULT_PREFIXES,
    exists: Callable[[str], bool] = os.path.exists,
) -> str | None:
    """Return the absolute path of `name` under the given prefixes, or None.

    `name` is a bare tool name ("sgdisk"), never a path: accepting a path here would
    let a caller smuggle `/tmp/sgdisk` past the prefix rule.
    """
    if not isinstance(name, str) or not name or os.sep in name:
        raise ValueError(f"{name!r} is not a bare tool name")
    if name not in trusted_basenames():
        raise ValueError(f"{name!r} is not a trusted tool")

    for prefix in prefixes:
        candidate = os.path.join(prefix, name)
        if exists(candidate):
            return candidate
    return None


def is_admissible_path(
    path: str,
    *,
    prefixes: Sequence[str] = DEFAULT_PREFIXES,
) -> tuple[bool, str]:
    """Whether an absolute tool path sits directly in an allowed prefix.

    Deliberately strict: the parent directory must be one of the prefixes verbatim,
    so `/usr/sbin/../tmp/sgdisk` and `/gnu/store/…/bin/../../tmp/sgdisk` are refused
    even though their basename and prefix look plausible.
    """
    if not isinstance(path, str) or not path.startswith(os.sep):
        return False, f"{path!r} is not an absolute path"
    if os.path.basename(path) not in trusted_basenames():
        return False, f"{os.path.basename(path)!r} is not a trusted tool"
    if os.path.dirname(path) not in set(prefixes):
        return False, f"{os.path.dirname(path)!r} is not one of the allowed tool prefixes"
    return True, ""
