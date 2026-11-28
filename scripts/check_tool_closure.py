# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that every tool the executor may run exists in the closure it will run in.

#280's last criterion: "абсолютний шлях у Python constant сам по собі не є доказом
наявності". A constant is a claim; this script turns it into an observation.

Run it with `--root` pointing at the tree that will actually execute the installer
— the Guix live image's root, a built profile, a staged rootfs — because existence
in the *build* environment proves nothing about the *image*.

Deliberate honesty about what a pass means:

* a pass proves the named paths exist and are executable **under --root**;
* it does not prove they are the right tools, that their argv is understood, or
  that they were built from the pinned sources;
* when --root is a host filesystem rather than the image, the result is about the
  host. The script says so instead of letting the number look like a closure proof.

This is not wired into `make check` or the release workflow on purpose. Today
TRUSTED_TOOLS uses FHS paths (`/usr/sbin/sgdisk`), and a Guix live image has no
/usr — so running this against a real closure would fail for a reason that is a
known open item (the paths have to move into the closure first), not because the
image is broken. Failing a release build over that would be the wrong signal.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.install_steps import TRUSTED_TOOLS  # noqa: E402


def check(root: Path) -> list[tuple[str, str]]:
    """Return (tool, problem) for every tool that is not usable under root."""
    problems: list[tuple[str, str]] = []
    for name, path in sorted(TRUSTED_TOOLS.items()):
        candidate = root / path.lstrip("/")
        if not candidate.exists():
            problems.append((name, f"{path} does not exist under {root}"))
            continue
        if not candidate.is_file():
            problems.append((name, f"{path} is not a regular file under {root}"))
            continue
        if not os.access(candidate, os.X_OK):
            problems.append((name, f"{path} is not executable under {root}"))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="tree that will execute the installer (a live image root, profile or staged rootfs)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the expected tools and exit, without checking anything",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, path in sorted(TRUSTED_TOOLS.items()):
            print(f"{name}\t{path}")
        return 0

    root = args.root
    if not root.is_dir():
        print(f"check-tool-closure: {root} is not a directory", file=sys.stderr)
        return 2

    problems = check(root)
    for name, problem in problems:
        print(f"check-tool-closure: {name}: {problem}", file=sys.stderr)

    print(
        f"check-tool-closure: {len(TRUSTED_TOOLS) - len(problems)}/{len(TRUSTED_TOOLS)} tools "
        f"usable under {root}"
    )
    if problems:
        print(
            "check-tool-closure: this proves nothing about the image unless --root IS the image",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
