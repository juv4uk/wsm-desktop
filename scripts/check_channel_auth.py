# SPDX-License-Identifier: LicenseRef-Volnist
"""Report whether the WSM Guix channel has the artefacts authentication needs.

The channel document says the trust bootstrap is not done. This prints what is
actually present, so the statement can be re-checked instead of trusted.

It deliberately does **not** decide whether the channel is authenticated:

* a signed introduction commit cannot be judged offline by a file listing;
* ``guix git authenticate`` is the only thing that proves it.

A regex over prose was tried first and produced five false positives out of five
- every hit was either a hedged statement or referred to the *Guix* channel lock
rather than this channel. A check that cries wolf gets ignored, so it is gone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ARTIFACTS = {
    "channel-metadata": ".guix-channel",
    "authorizations": ".guix-authorizations",
    "channel-doc": "docs/GUIX-CHANNEL.md",
}


def keyring_branches(root: Path) -> list[str]:
    """Branches that carry the channel keyring, as the channel spec expects."""
    try:
        completed = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)"],
            cwd=root, capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [
        line.strip() for line in completed.stdout.splitlines()
        if line.strip().endswith("keyring")
    ]


def inspect(root: Path) -> dict[str, object]:
    present = {name: (root / path).is_file() for name, path in ARTIFACTS.items()}
    branches = keyring_branches(root)
    missing = [name for name, value in present.items() if not value]
    if not branches:
        missing.append("keyring-branch")
    return {
        "schema": "wsm-channel-artifacts/1",
        "present": present,
        "keyring_branches": branches,
        "missing": missing,
        "artifacts_complete": not missing,
        "authenticated": "unknown - only guix git authenticate can decide",
    }


def main(argv: list[str] | None = None) -> int:
    root = Path((argv or sys.argv[1:] or ["."])[0]).resolve()
    state = inspect(root)

    for name, value in state["present"].items():
        print(f"check-channel-artifacts: {name}: {value}")
    print(f"check-channel-artifacts: keyring-branch: {state['keyring_branches'] or False}")
    if state["missing"]:
        print(
            "check-channel-artifacts: missing before any authentication claim: "
            + ", ".join(state["missing"])
        )
    else:
        print(
            "check-channel-artifacts: all artefacts present; run "
            "`guix git authenticate` to decide authentication"
        )
    print("check-channel-artifacts: authenticated: unknown by design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
