# SPDX-License-Identifier: LicenseRef-Volnist
"""Catch Scheme helpers used without the module that defines them.

Two builds in a row failed at *read* time, not at build time:

* ``(srfi srfi-1)`` missing for ``any``;
* ``(guix utils)`` missing for ``version-major+minor``.

Neither is visible by reading the file: the code looks right, and the failure
only appears when Guix evaluates it - twenty minutes into a build.

This checker does not replace evaluation. It catches the small, known set of
helpers that Guix exports from specific modules, which is exactly the set that
has bitten this repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Helper -> module that must be imported for it to exist.
KNOWN_HELPERS: dict[str, str] = {
    "version-major+minor": "guix utils",
    "version-major": "guix utils",
    "version-minor": "guix utils",
    "package-version": "guix packages",
    "string-contains": "srfi srfi-13",
    "string-join": "srfi srfi-13",
    "string-trim-both": "srfi srfi-13",
    "any": "srfi srfi-1",
    "every": "srfi srfi-1",
    "filter": "srfi srfi-1",
    "fold": "srfi srfi-1",
}

IMPORT = re.compile(r"#:use-module\s+\(([^)]+)\)|\(use-modules\s+(.*?)\)", re.DOTALL)


def imported_modules(text: str) -> set[str]:
    modules: set[str] = set()
    for match in IMPORT.finditer(text):
        chunk = match.group(1) or match.group(2) or ""
        for line in chunk.splitlines():
            cleaned = line.strip().strip("()").strip()
            if cleaned.startswith("("):
                cleaned = cleaned.strip("()")
            if cleaned and not cleaned.startswith(";"):
                modules.add(" ".join(cleaned.split()))
    return modules


def code_lines(text: str) -> list[tuple[int, str]]:
    """Lines that are not comments: a mention in a comment is documentation."""
    result: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(";") or stripped.startswith("#|"):
            continue
        result.append((number, line))
    return result


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    modules = imported_modules(text)
    problems: list[str] = []
    for number, line in code_lines(text):
        # Ignore the comment tail of a code line.
        code = line.split(";", 1)[0]
        for helper, module in KNOWN_HELPERS.items():
            if not re.search(rf"(?<![\w-]){re.escape(helper)}(?![\w-])", code):
                continue
            if module not in modules:
                problems.append(
                    f"{path}:{number}: uses {helper} but does not import ({module})"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    roots = [Path(arg) for arg in (argv or sys.argv[1:])] or [Path("systems"), Path("wsm")]
    problems: list[str] = []
    for root in roots:
        if root.is_file():
            problems.extend(check(root))
            continue
        if not root.is_dir():
            # A missing root scans nothing and prints success. That is the same
            # silent hole as a collector that covers nothing: the check passes
            # because it did not look, not because there was nothing to find.
            problems.append(f"{root}: root does not exist, so nothing was scanned")
            continue
        for path in sorted(root.rglob("*.scm")):
            problems.extend(check(path))
    for problem in problems:
        print(f"check-scheme-imports: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("check-scheme-imports: every known helper has its module imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
