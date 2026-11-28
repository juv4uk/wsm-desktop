#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that Scheme files are structurally balanced before Guix ever sees them.

The repository's Scheme is validated by `guix` evaluation, which only runs in CI
and takes minutes. A missing parenthesis therefore surfaces late, in a job that
also builds profiles - and the error message points at the end of a file rather
than at the mistake.

This is not a Scheme reader and does not pretend to be one. It tokenises far
enough to ignore what must be ignored - strings, `;` comments, `#| |#` blocks,
character literals such as `#\\(`, and `#;` datum comments - and then reports an
unbalanced form with the line where the imbalance was noticed and the line of the
form that was never closed.
"""

from __future__ import annotations

import sys
from pathlib import Path

OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {")": "(", "]": "[", "}": "{"}


class Imbalance(Exception):
    def __init__(self, path: Path, line: int, column: int, message: str) -> None:
        super().__init__(f"{path}:{line}:{column}: {message}")
        self.path = path
        self.line = line
        self.column = column
        self.message = message


CONFLICT_MARKERS = ("<<<<<<< ", ">>>>>>> ", "||||||| ")


def scan(path: Path, source: str) -> None:
    """Raise Imbalance if the source is not balanced. Ignores strings and comments.

    Also refuses a committed merge conflict. Balanced parentheses say nothing
    about that: `ci/cuirass/images.scm` reached main with `<<<<<<< HEAD` in it and
    this check passed, because a conflict marker is not a paren problem.
    """
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(CONFLICT_MARKERS) or stripped == "=======":
            raise Imbalance(path, number, 1, f"committed merge conflict marker: {stripped[:20]!r}")
    stack: list[tuple[str, int, int]] = []
    index = 0
    line = 1
    column = 1
    length = len(source)

    def advance(count: int = 1) -> None:
        nonlocal index, line, column
        for _ in range(count):
            if index < length and source[index] == "\n":
                line += 1
                column = 1
            else:
                column += 1
            index += 1

    while index < length:
        char = source[index]

        # line comment
        if char == ";":
            while index < length and source[index] != "\n":
                advance()
            continue

        # block comment, possibly nested
        if source.startswith("#|", index):
            depth = 1
            advance(2)
            while index < length and depth:
                if source.startswith("#|", index):
                    depth += 1
                    advance(2)
                elif source.startswith("|#", index):
                    depth -= 1
                    advance(2)
                else:
                    advance()
            if depth:
                raise Imbalance(path, line, column, "unterminated #| block comment")
            continue

        # datum comment: #; skips exactly one following datum
        if source.startswith("#;", index):
            advance(2)
            # skip whitespace, then one form (balanced or an atom)
            while index < length and source[index].isspace():
                advance()
            if index < length and source[index] in OPENERS:
                depth = 0
                while index < length:
                    inner = source[index]
                    if inner == '"':
                        advance()
                        while index < length and source[index] != '"':
                            if source[index] == "\\":
                                advance()
                            advance()
                        advance()
                        continue
                    if inner in OPENERS:
                        depth += 1
                    elif inner in CLOSERS:
                        depth -= 1
                        advance()
                        if depth == 0:
                            break
                        continue
                    advance()
            else:
                while index < length and not source[index].isspace() and source[index] not in CLOSERS:
                    advance()
            continue

        # string, with escapes
        if char == '"':
            start_line, start_column = line, column
            advance()
            closed = False
            while index < length:
                if source[index] == "\\":
                    advance(2)
                    continue
                if source[index] == '"':
                    advance()
                    closed = True
                    break
                advance()
            if not closed:
                raise Imbalance(path, start_line, start_column, "unterminated string")
            continue

        # character literal: #\( is the character "(", #\space is a named one
        if source.startswith("#\\", index):
            advance(2)
            if index < length:
                if source[index].isalpha():
                    while index < length and (source[index].isalnum() or source[index] == "-"):
                        advance()
                else:
                    advance()
            continue

        if char in OPENERS:
            stack.append((char, line, column))
            advance()
            continue

        if char in CLOSERS:
            if not stack:
                raise Imbalance(path, line, column, f"unexpected '{char}'")
            opener, open_line, open_column = stack.pop()
            if OPENERS[opener] != char:
                raise Imbalance(
                    path,
                    line,
                    column,
                    f"'{char}' closes '{opener}' opened at {open_line}:{open_column}",
                )
            advance()
            continue

        advance()

    if stack:
        opener, open_line, open_column = stack[-1]
        raise Imbalance(
            path,
            open_line,
            open_column,
            f"'{opener}' opened here is never closed ({len(stack)} form(s) left open)",
        )


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    targets = [Path(item) for item in argv] if argv else sorted(root.rglob("*.scm"))
    targets = [path for path in targets if path.is_file()]

    failures = 0
    for path in targets:
        try:
            scan(path, path.read_text(encoding="utf-8"))
        except Imbalance as problem:
            print(f"SCHEME-SYNTAX-FAIL: {problem}", file=sys.stderr)
            failures += 1

    if failures:
        return 1
    print(f"SCHEME-SYNTAX-PASS: {len(targets)} file(s) balanced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
