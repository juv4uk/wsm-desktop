# SPDX-License-Identifier: LicenseRef-Volnist
"""Every Scheme module under wsm/ must be loaded by the Guix evaluation test.

The checker deliberately remains smaller than a Scheme parser. Before looking
for module forms it masks lexical regions that cannot contain executable forms:
line comments, nested block comments, strings, and character literals.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MODULE_ROOT = Path("wsm")
EVALUATION_TEST = Path("tests/guix/source-module-evaluation.scm")

DEFINE_MODULE = re.compile(r"\(define-module\s+\(([^)]+)\)")
USE_MODULES_HEAD = re.compile(r"\(use-modules\b")


def mask_scheme_non_code(text: str) -> str:
    """Blank comments, strings and character literals while preserving offsets.

    Guile accepts nested #| ... |# comments. String escapes are consumed in
    pairs so an escaped quote cannot accidentally end the string. Newlines are
    preserved to keep diagnostics and source positions stable.
    """
    chars = list(text)
    index = 0
    block_depth = 0
    in_string = False

    def blank(position: int) -> None:
        if text[position] != "\n":
            chars[position] = " "

    while index < len(text):
        if in_string:
            if text[index] == "\\":
                blank(index)
                index += 1
                if index < len(text):
                    blank(index)
                    index += 1
            elif text[index] == '"':
                blank(index)
                in_string = False
                index += 1
            else:
                blank(index)
                index += 1
            continue

        if block_depth:
            if text.startswith("#|", index):
                blank(index)
                blank(index + 1)
                block_depth += 1
                index += 2
            elif text.startswith("|#", index):
                blank(index)
                blank(index + 1)
                block_depth -= 1
                index += 2
            else:
                blank(index)
                index += 1
            continue

        if text.startswith("#|", index):
            blank(index)
            blank(index + 1)
            block_depth = 1
            index += 2
        elif text[index] == ";":
            while index < len(text) and text[index] != "\n":
                blank(index)
                index += 1
        elif text[index] == '"':
            blank(index)
            in_string = True
            index += 1
        elif text.startswith("#\\", index):
            # Protect punctuation in literals such as #\), #\; and #\".
            blank(index)
            blank(index + 1)
            index += 2
            if index < len(text):
                blank(index)
                index += 1
        else:
            index += 1

    return "".join(chars)


def _balanced(text: str, start: int) -> str | None:
    """Return the inside of the form whose '(' is at start."""
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
    """Every immediate (...) inside block, as text."""
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


def declared_modules(root: Path) -> dict[str, Path]:
    """Module name -> file, taken from the file's own define-module."""
    found: dict[str, Path] = {}
    for path in sorted((root / MODULE_ROOT).rglob("*.scm")):
        text = mask_scheme_non_code(path.read_text(encoding="utf-8"))
        match = DEFINE_MODULE.search(text)
        if match is None:
            continue
        module = " ".join(match.group(1).split())
        relative = path.relative_to(root)
        previous = found.get(module)
        if previous is not None:
            raise ValueError(
                f"duplicate Scheme module {module!r}: {previous} and {relative}"
            )
        found[module] = relative
    return found


def imported_modules(root: Path, test: Path = EVALUATION_TEST) -> set[str]:
    text = mask_scheme_non_code((root / test).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for head in USE_MODULES_HEAD.finditer(text):
        block = _balanced(text, head.start())
        if block is None:
            continue
        imported.update(_top_level_forms(block))
    return imported


def check(root: Path, test: Path = EVALUATION_TEST) -> list[str]:
    """Return a problem line per module the evaluation test does not load."""
    try:
        modules = declared_modules(root)
    except ValueError as error:
        return [str(error)]
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
