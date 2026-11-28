# SPDX-License-Identifier: LicenseRef-Volnist
"""Report how far a branch has drifted from its base.

CONTRIBUTING.md already says "start from current main and synchronise the branch
before marking a PR ready". The rule was not measurable, so six pull requests sat
open simultaneously, each conflicting with the others, and every merge broke the
rest.

This reports the drift. It deliberately does **not** fail the build: a long-lived
branch is a judgement call, and a gate that blocks honest work gets bypassed.
What it removes is the excuse "I did not know it was 148 commits behind".
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git failed")
    return completed.stdout


def behind_count(root: Path, base: str, head: str) -> int:
    """Commits on BASE that are not on HEAD."""
    output = run_git(root, "rev-list", "--count", f"{head}..{base}")
    return int(output.strip() or "0")


def ahead_count(root: Path, base: str, head: str) -> int:
    output = run_git(root, "rev-list", "--count", f"{base}..{head}")
    return int(output.strip() or "0")


def verdict(behind: int, ahead: int, soft_limit: int) -> str:
    if behind == 0:
        return "up to date with the base branch"
    if behind <= soft_limit:
        return f"{behind} commits behind: rebase before marking ready"
    return (
        f"{behind} commits behind: this branch predates {behind} commits of the "
        "base and will conflict. Rebase onto the base and re-run the suite "
        "before asking for review"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check-branch-freshness", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--soft-limit", type=int, default=20)
    args = parser.parse_args(argv)

    try:
        behind = behind_count(args.root, args.base, args.head)
        ahead = ahead_count(args.root, args.base, args.head)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"check-branch-freshness: cannot measure drift: {exc}", file=sys.stderr)
        return 2

    print(f"check-branch-freshness: {ahead} ahead, {behind} behind {args.base}")
    print(f"check-branch-freshness: {verdict(behind, ahead, args.soft_limit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
