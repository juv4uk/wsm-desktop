# SPDX-License-Identifier: LicenseRef-Volnist
"""Refuse a channel lock that is not free-only and authenticated.

`channels.lock.scm` decides what ends up inside the image. It is four lines of
Scheme that a pull request can quietly extend, and nothing in `make check`
notices - until an image ships with a third-party channel in it.

That is the Omarchy 4.0.0 lesson in its most expensive form: a third-party
theme from a git repository was code execution (CVE-2026-108913). A third-party
Guix channel is the same thing at a bigger scale - it replaces packages.

The rules are deliberately narrow:

* only official GNU Guix channels;
* every URL is https on an allow-listed host;
* every channel carries an introduction, so commits are authenticated;
* every commit is a full 40-character hash, not a branch name.

A comment saying "free only" is not evidence. This reads the forms.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Two products, two policies.
#
# WSM ships a comfortable desktop out of the box, and that includes proprietary
# drivers - so Nonguix is not an accident to be forbidden, it is part of the
# Compatibility image. What must never happen is an *unnamed* third-party
# channel, or one that is unpinned or unauthenticated.
#
# The free image keeps its own lock and stays free; the compatibility image has
# a separate lock that names Nonguix explicitly.
POLICIES: dict[str, dict[str, set[str]]] = {
    "free": {
        "channels": {"guix"},
        "hosts": {"git.guix.gnu.org", "git.savannah.gnu.org"},
    },
    "compatibility": {
        "channels": {"guix", "nonguix"},
        "hosts": {
            "git.guix.gnu.org",
            "git.savannah.gnu.org",
            "gitlab.com",
            "codeberg.org",
        },
    },
}
DEFAULT_POLICY = "free"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "channels.lock.scm"


class ParseError(Exception):
    pass


def tokenize(text: str) -> list[str]:
    """Split Scheme into tokens, dropping comments. Enough for a channel lock."""
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == ";":
            while index < len(text) and text[index] != "\n":
                index += 1
        elif char.isspace():
            index += 1
        elif char in "()":
            tokens.append(char)
            index += 1
        elif char == '"':
            end = index + 1
            buffer = []
            while end < len(text) and text[end] != '"':
                if text[end] == "\\" and end + 1 < len(text):
                    buffer.append(text[end + 1])
                    end += 2
                    continue
                buffer.append(text[end])
                end += 1
            tokens.append('"' + "".join(buffer) + '"')
            index = end + 1
        else:
            end = index
            while end < len(text) and not text[end].isspace() and text[end] not in '();':
                end += 1
            tokens.append(text[index:end])
            index = end
    return tokens


def parse(tokens: list[str]) -> Any:
    def read(position: int) -> tuple[Any, int]:
        if position >= len(tokens):
            raise ParseError("unexpected end of input")
        token = tokens[position]
        if token == "(":
            items = []
            position += 1
            while True:
                if position >= len(tokens):
                    raise ParseError("unbalanced parentheses")
                if tokens[position] == ")":
                    return items, position + 1
                item, position = read(position)
                items.append(item)
        if token == ")":
            raise ParseError("unexpected )")
        if token.startswith('"'):
            return token[1:-1], position + 1
        return token, position + 1

    value, position = read(0)
    if position != len(tokens):
        raise ParseError("trailing tokens after the first form")
    return value


def channels_of(form: Any) -> list[dict[str, Any]]:
    """Turn (list (channel (name 'guix) ...)) into plain dictionaries."""
    if not isinstance(form, list) or not form or form[0] != "list":
        raise ParseError("expected (list (channel ...) ...)")

    found: list[dict[str, Any]] = []
    for entry in form[1:]:
        if not isinstance(entry, list) or not entry or entry[0] != "channel":
            raise ParseError(f"unexpected entry: {entry!r}")
        channel: dict[str, Any] = {}
        for field in entry[1:]:
            if not isinstance(field, list) or not field:
                continue
            key = field[0]
            if key in {"name", "url", "branch", "commit"} and len(field) > 1:
                value = field[1]
                channel[key] = value[1:] if isinstance(value, str) and value.startswith("'") else value
            elif key == "introduction":
                channel["introduction"] = field[1:]
        found.append(channel)
    return found


def check(text: str, policy: str = DEFAULT_POLICY) -> list[str]:
    """Return every reason this lock is not acceptable. Empty means acceptable."""
    if policy not in POLICIES:
        return [f"unknown policy {policy!r}; choose one of {sorted(POLICIES)}"]
    rules = POLICIES[policy]
    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    problems: list[str] = []
    if not channels:
        problems.append("the lock declares no channels")

    for channel in channels:
        name = channel.get("name", "<unnamed>")
        if name not in rules["channels"]:
            problems.append(
                f"channel {name!r} is not an official Guix channel; a third-party "
                "channel replaces packages and is code execution"
            )

        url = channel.get("url", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            problems.append(f"channel {name!r} is not fetched over https: {url!r}")
        else:
            host = url.split("/")[2]
            if host not in rules["hosts"]:
                problems.append(f"channel {name!r} uses an unexpected host: {host!r}")

        commit = channel.get("commit")
        if not isinstance(commit, str) or not COMMIT.match(commit):
            problems.append(
                f"channel {name!r} is not pinned to a full commit: {commit!r}"
            )

        introduction = channel.get("introduction")
        if not introduction:
            problems.append(
                f"channel {name!r} has no introduction, so its commits are not authenticated"
            )
        else:
            blob = " ".join(str(part) for part in introduction)
            if "openpgp-fingerprint" not in blob and "openpgp" not in blob:
                problems.append(f"channel {name!r} introduction carries no OpenPGP fingerprint")

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description="Verify that channels.lock.scm is free-only, https and authenticated.",
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default=DEFAULT_POLICY,
        help="free: official Guix only; compatibility: Guix plus an explicitly named Nonguix",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = args.lock.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-channels: cannot read {args.lock}: {exc}", file=sys.stderr)
        return 2

    problems = check(text, args.policy)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {args.lock.name} satisfies the {args.policy} policy "
        "(https, pinned commit, authenticated introduction)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
