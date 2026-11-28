# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that every tool the executor may run exists in the closure it will run in.

#280's last criterion: "абсолютний шлях у Python constant сам по собі не є доказом
наявності". A constant is a claim; this script turns it into an observation.

Run it with `--root` pointing at the tree that will actually execute the installer
— the Guix live image's root, a built profile, a staged rootfs — because existence
in the *build* environment proves nothing about the *image*.

Two ways to name the tools:

* without `--prefix`, the FHS paths in `TRUSTED_TOOLS` (`/usr/sbin/sgdisk`) are
  checked under `--root`;
* with one or more `--prefix` options, each trusted basename is resolved inside
  those directories under `--root`, by the same rule `wsm_install.tools.resolve`
  applies when `plan_steps(tool_prefixes=...)` builds a plan. This is the form a
  Guix image needs, because it has no `/usr` at all.

Deliberate honesty about what a pass means:

* a pass proves the named paths exist and are executable **under --root**;
* it does not prove they are the right tools, that their argv is understood, or
  that they were built from the pinned sources;
* when --root is a host filesystem rather than the image, the result is about the
  host, and the script says so instead of letting the number look like a closure
  proof.

What CI runs, and what it does not:

`make check-tool-closure` (and therefore `make check` and the CI job) runs
`--self-check`. That builds throwaway roots in a temporary directory and asserts
this checker's behaviour — pass on a complete root, a named failure for a missing
or non-executable tool, and a pass in `--prefix` mode for a Guix-shaped root with
no `/usr`. It proves the *checker* works. It proves nothing about any image, and
it says so on every run.

The image check itself is still not a release gate, on purpose. `TRUSTED_TOOLS`
uses FHS paths (`/usr/sbin/sgdisk`), the minimal live image ships neither
`/usr` nor those packages yet, and `scripts/build_iso.sh` produces an ISO without
leaving a system profile root behind. Failing a release build over that would be
the wrong signal for a known open item: the paths have to move into the closure
first. Until then, run this by hand against the built image:

    python3 scripts/check_tool_closure.py --root /mnt/image \\
        --prefix /run/current-system/profile/bin \\
        --prefix /run/current-system/profile/sbin
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.install_steps import TRUSTED_TOOLS  # noqa: E402
from wsm_install.tools import resolve  # noqa: E402


def _problem(name: str, root: Path, path: str) -> list[tuple[str, str]]:
    """Why `path` is not usable under `root`, as a one-element list, or nothing."""
    candidate = root / path.lstrip("/")
    if not candidate.exists():
        return [(name, f"{path} does not exist under {root}")]
    if not candidate.is_file():
        return [(name, f"{path} is not a regular file under {root}")]
    if not os.access(candidate, os.X_OK):
        return [(name, f"{path} is not executable under {root}")]
    return []


def check(root: Path, prefixes: Sequence[str] | None = None) -> list[tuple[str, str]]:
    """Return (tool, problem) for every tool that is not usable under root.

    With `prefixes`, a tool is located by `wsm_install.tools.resolve` inside those
    directories under `root`; without them, by the FHS path in the table.
    """
    problems: list[tuple[str, str]] = []
    for name, path in sorted(TRUSTED_TOOLS.items()):
        if prefixes is None:
            problems.extend(_problem(name, root, path))
            continue
        expected = resolve(
            name,
            prefixes=prefixes,
            exists=lambda candidate: (root / candidate.lstrip("/")).exists(),
        )
        if expected is None:
            problems.append(
                (name, f"not found in any of {list(prefixes)} under {root}")
            )
            continue
        problems.extend(_problem(name, root, expected))
    return problems


def describes_host_root(root: Path) -> bool:
    """Whether `root` is this machine's own filesystem root.

    A run against it says something true about the host and nothing about any
    image, which is exactly the confusion this script exists to prevent.
    """
    try:
        return root.resolve() == Path("/").resolve()
    except OSError:  # pragma: no cover - resolve() on a plain path does not raise
        return False


def _populate(root: Path, paths: Sequence[str], mode: int = 0o755) -> None:
    """Create an executable file at each FHS path, inside `root`."""
    for path in paths:
        target = root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(mode)


def _capture(argv: list[str]) -> tuple[int, str, str]:
    """Run main() and return (exit code, stdout, stderr) instead of printing."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def self_check() -> int:
    """Assert this checker's own behaviour on throwaway roots.

    Red if the checker stops noticing a missing or non-executable tool, if it
    starts pretending a Guix-shaped root (no `/usr`) is complete in FHS mode, or
    if `--prefix` stops finding tools that `resolve` would find.
    """
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)

        # 1. A complete FHS root passes, and the exit code says so.
        fhs = base / "fhs"
        _populate(fhs, list(TRUSTED_TOOLS.values()))
        expect(check(fhs) == [], "a complete root must report no problems")
        code, out, _ = _capture(["--root", str(fhs)])
        expect(code == 0, f"a complete root must exit 0, got {code}")
        expect(
            f"{len(TRUSTED_TOOLS)}/{len(TRUSTED_TOOLS)} tools usable" in out,
            "a passing run must report the usable count",
        )

        # 2. A missing tool is named, and the run fails.
        missing = base / "missing"
        _populate(
            missing,
            [p for n, p in TRUSTED_TOOLS.items() if n != "sgdisk"],
        )
        problems = check(missing)
        expect(
            [name for name, _ in problems] == ["sgdisk"],
            f"a missing sgdisk must be the only problem, got {problems}",
        )
        code, _, err = _capture(["--root", str(missing)])
        expect(code == 1, f"an incomplete root must exit 1, got {code}")
        expect("sgdisk" in err, "the failing tool must be named on stderr")

        # 3. A non-executable tool is named as such, not as absent.
        nonexec = base / "nonexec"
        _populate(nonexec, list(TRUSTED_TOOLS.values()))
        target = nonexec / TRUSTED_TOOLS["mount"].lstrip("/")
        target.chmod(0o644)
        problems = check(nonexec)
        expect(
            [name for name, _ in problems] == ["mount"]
            and "not executable" in problems[0][1],
            f"a non-executable mount must be named as such, got {problems}",
        )

        # 4. A Guix-shaped root has no /usr: FHS mode must not call it complete,
        #    and --prefix mode must verify the same tools in the profile.
        guix = base / "guix"
        profile = "/run/current-system/profile/bin"
        _populate(guix, [f"{profile}/{name}" for name in TRUSTED_TOOLS])
        expect(
            len(check(guix)) == len(TRUSTED_TOOLS),
            "FHS mode must not pass a root that has no /usr",
        )
        expect(
            check(guix, prefixes=(profile,)) == [],
            "--prefix mode must find the tools in the image profile",
        )
        code, _, _ = _capture(["--root", str(guix), "--prefix", profile])
        expect(code == 0, f"--prefix mode must exit 0 for a complete profile, got {code}")
        code, _, err = _capture(["--root", str(guix)])
        expect(
            code == 1 and "does not exist" in err,
            "FHS mode against a Guix-shaped root must fail and say why",
        )

        # 5. A root that is not a directory is refused, not reported as complete.
        not_a_dir = base / "file"
        not_a_dir.write_text("not a tree\n", encoding="utf-8")
        code, _, err = _capture(["--root", str(not_a_dir)])
        expect(code == 2, f"a non-directory root must exit 2, got {code}")
        expect("is not a directory" in err, "a non-directory root must be named")

        # 6. --list prints every expected tool and checks nothing.
        code, out, _ = _capture(["--list"])
        expect(code == 0, f"--list must exit 0, got {code}")
        expect(
            len([line for line in out.splitlines() if line.strip()]) == len(TRUSTED_TOOLS),
            "--list must print one line per trusted tool",
        )

    if failures:
        for failure in failures:
            print(f"check-tool-closure: self-check failed: {failure}", file=sys.stderr)
        return 1

    print("check-tool-closure: self-check OK (6 cases)")
    print(
        "check-tool-closure: NOTE this proves the checker, not an image: it ran against "
        "throwaway roots. For a closure result, run --root <image root> "
        "(and --prefix <image profile dir>) on the built image.",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="tree that will execute the installer (a live image root, profile or staged rootfs)",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "resolve each trusted tool inside DIR under --root instead of using the "
            "FHS path in the table; repeatable, first hit wins. Use it for a Guix "
            "image, which has no /usr."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the expected tools and exit, without checking anything",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "assert this checker's behaviour on throwaway roots and exit; "
            "verifies the checker, never an image"
        ),
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, path in sorted(TRUSTED_TOOLS.items()):
            print(f"{name}\t{path}")
        return 0

    if args.self_check:
        return self_check()

    root = args.root
    if not root.is_dir():
        print(f"check-tool-closure: {root} is not a directory", file=sys.stderr)
        return 2

    problems = check(root, prefixes=args.prefix)
    for name, problem in problems:
        print(f"check-tool-closure: {name}: {problem}", file=sys.stderr)

    scope = f"under {root}"
    if args.prefix:
        scope = f"in {list(args.prefix)} under {root}"
    print(
        f"check-tool-closure: {len(TRUSTED_TOOLS) - len(problems)}/{len(TRUSTED_TOOLS)} tools "
        f"usable {scope}"
    )
    if describes_host_root(root):
        print(
            "check-tool-closure: --root is this host's /: the result describes the host, "
            "not any image",
            file=sys.stderr,
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
