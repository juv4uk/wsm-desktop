# SPDX-License-Identifier: LicenseRef-Volnist
"""Hold Pascal sources to the contract the build workflow assumes.

Free Pascal compiles a file that has no licence header, no mode directive and no
program name, and the result is a binary nobody can trace back to this repository. The
compiler will not tell you any of that; this does.

Checked for every tracked `*.pas`, `*.pp` and `*.lpr` outside `third_party/`:

  * an SPDX line naming LicenseRef-Volnist, because the repository licence is ВОЛЬНІСТЬ
    and a Pascal file is work created for WSM Desktop like any other;
  * an explicit `{$mode ...}` directive, because the default mode changes with the
    compiler invocation and a file that compiles under one `-M` flag and not another is
    a trap for whoever builds it next;
  * a `program`/`unit`/`library` keyword matching the file, because a unit named
    differently from its file is accepted by fpc and then cannot be found by anything
    else;
  * no `{$IFDEF DEBUG}` block that writes to stdout, because a diagnostic line on stdout
    corrupts the JSON the collectors emit;
  * no two-element character set where a range was meant. `['0', '9']` accepts only the
    characters 0 and 9, which reads as the digit range and is not one. Three bugs of
    exactly this shape reached CI before the parity harness found them.

Exit 1 with the file and the reason. Nothing here needs a compiler, which is the point:
it runs where fpc is not installed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = (".pas", ".pp", ".lpr")
SPDX = "LicenseRef-Volnist"

MODE_DIRECTIVE = re.compile(r"\{\$mode\s+(objfpc|delphi|fpc|tp|macpas|iso)\}", re.IGNORECASE)
DECLARATION = re.compile(r"^\s*(program|unit|library)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE | re.MULTILINE)
STDOUT_DEBUG = re.compile(r"\{\$ifdef\s+DEBUG\}", re.IGNORECASE)
# `['0', '9']` is a set of two characters; `['0'..'9']` is the digit range. The first
# spelling looks like the second and silently rejects everything between them. Three
# separate bugs of this shape reached CI before anyone noticed.
TWO_CHAR_SET = re.compile(r"\[\s*'(.)'\s*,\s*'(.)'\s*\]")


def tracked_sources(root: Path) -> list[Path]:
    """Every tracked Pascal source outside third_party, or every file if git is absent."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "*.pas", "*.pp", "*.lpr"],
            cwd=str(root), capture_output=True, text=True, check=True,
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        listed = [str(p.relative_to(root)) for suffix in SOURCE_SUFFIXES
                  for p in root.rglob(f"*{suffix}")]
    return [root / name for name in listed if not name.startswith("third_party/")]


def check(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:10])

    if SPDX not in head:
        problems.append(f"{path}: no '{SPDX}' line in the first ten lines")

    if not MODE_DIRECTIVE.search(text):
        problems.append(f"{path}: no explicit {{$mode ...}} directive")

    declaration = DECLARATION.search(text)
    if declaration is None:
        problems.append(f"{path}: no program/unit/library declaration")
    else:
        expected = path.stem.lower()
        actual = declaration.group(2).lower()
        if actual != expected:
            problems.append(
                f"{path}: declares '{actual}' but the file is '{expected}'"
            )

    for match in TWO_CHAR_SET.finditer(text):
        low, high = match.group(1), match.group(2)
        # Adjacent letters ('a', 'b') and any two digits in order ('0', '9') both read
        # as a range and are not one.
        if ord(low) < ord(high) and (
            (low.isdigit() and high.isdigit())
            or (low.isalpha() and high.isalpha() and ord(high) - ord(low) <= 25)
        ):
            line = text[:match.start()].count("\n") + 1
            problems.append(
                f"{path}:{line}: set [{low!r}, {high!r}] is two characters, not the "
                f"range '{low}'..'{high}'; write ['{low}'..'{high}'] if the range is meant"
            )

    if STDOUT_DEBUG.search(text):
        problems.append(
            f"{path}: has a {{$ifdef DEBUG}} block; a debug line on stdout corrupts "
            "the JSON these programs emit"
        )
    return problems


def main() -> int:
    sources = tracked_sources(ROOT)
    if not sources:
        print("no Pascal sources yet; nothing to check")
        return 0

    problems: list[str] = []
    for source in sources:
        problems.extend(check(source))

    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"checked {len(sources)} Pascal source(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
