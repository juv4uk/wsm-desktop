# SPDX-License-Identifier: LicenseRef-Volnist
"""Every Scheme module under ``wsm/`` must be loaded by the Guix evaluation test.

The repository has two independent ways a module can be broken and only one of
them is visible without Guix:

* a *static* break (missing ``#:use-module``) is caught by
  ``check_scheme_imports.py`` without Guix;
* a *load* break - wrong module path, a name that Guix does not export, an
  ``#:export`` of something undefined - appears only when Guix actually
  evaluates the file, twenty minutes into a build.

``tests/guix/source-module-evaluation.scm`` is the only place that evaluates
source modules for real. If a new module is added and nobody adds it there, the
evaluation keeps passing while covering less - the coverage silently shrinks and
the test looks green.

This checker keeps that from happening: it reads every ``define-module`` under
``wsm/`` and requires the evaluation test to ``use-modules`` each one.

It does not evaluate anything itself and does not replace the Guix run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MODULE_ROOT = Path("wsm")
EVALUATION_TEST = Path("tests/guix/source-module-evaluation.scm")

DEFINE_MODULE = re.compile(r"\(define-module\s+\(([^)]+)\)")
USE_MODULES_HEAD = re.compile(r"\(use-modules\b")


def _balanced(text: str, start: int) -> str | None:
    """Return the inside of the form whose '(' is at ``start``."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    return None


def _top_level_forms(block: str) -> list[str]:
    """Every immediate ``(...)`` inside ``block``, as text."""
    forms: list[str] = []
    index = 0
    while index < len(block):
        if block[index] != "(":
            index += 1
            continue
        inner = _balanced(block, index)
        if inner is None:
            break
        forms.append(" ".join(inner.split()))
        index += len(inner) + 2
    return forms


def module_name(path: Path) -> str:
    """``wsm/packages/wsm.scm`` -> ``wsm packages wsm``."""
    return " ".join(path.with_suffix("").parts)


def declared_modules(root: Path) -> dict[str, Path]:
    """Module name -> file, taken from the file's own ``define-module``."""
    found: dict[str, Path] = {}
    for path in sorted((root / MODULE_ROOT).rglob("*.scm")):
        text = path.read_text(encoding="utf-8")
        match = DEFINE_MODULE.search(text)
        if match is None:
            continue
        found[" ".join(match.group(1).split())] = path.relative_to(root)
    return found


def imported_modules(root: Path, test: Path = EVALUATION_TEST) -> set[str]:
    text = (root / test).read_text(encoding="utf-8")
    imported: set[str] = set()
    for head in USE_MODULES_HEAD.finditer(text):
        block = _balanced(text, head.start())
        if block is None:
            continue
        imported.update(_top_level_forms(block))
    return imported


def check(root: Path, test: Path = EVALUATION_TEST) -> list[str]:
    """Return a problem line per module the evaluation test does not load."""
    modules = declared_modules(root)
    if not modules:
        return [f"no (define-module ...) found under {MODULE_ROOT}/"]
    if not (root / test).is_file():
        return [f"missing evaluation test {test}"]

    imported = imported_modules(root, test)
    return [
        f"{module} ({path}) is not loaded by {test}"
        for module, path in sorted(modules.items())
        if module not in imported
    ]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = check(root)
    if problems:
        for problem in problems:
            print(f"SCHEME-MODULE-COVERAGE: {problem}", file=sys.stderr)
        print(
            "SCHEME-MODULE-COVERAGE-FAIL: a module nobody evaluates is a module "
            "nobody has checked.",
            file=sys.stderr,
        )
        return 1
    print("SCHEME-MODULE-COVERAGE-PASS: every wsm/ module is loaded by the Guix evaluation test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
