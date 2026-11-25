# SPDX-License-Identifier: LicenseRef-Volnist
"""Check the structural policy of the Free Guix channel lock.

This is not a cryptographic signature verifier. Guix channel authentication
must still be performed by guix time-machine with authentication enabled.
This script rejects accidental or unreviewed additions to the Free lock before
they reach the image build.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ALLOWED_CHANNELS = {"guix"}
ALLOWED_REPOSITORIES = {
    "https://git.guix.gnu.org/guix.git",
    "https://git.savannah.gnu.org/git/guix.git",
}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
INTRODUCTION_COMMIT = "9edb3f66fd807b096b48283debdcddccfea34bad"
INTRODUCTION_FINGERPRINT = "BBB02DDF2CEAF6A80D1DE643A2A06DF2A33A54FA"
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "channels.lock.scm"
REQUIRED_FIELDS = {"name", "url", "branch", "commit", "introduction"}


class ParseError(Exception):
    pass


class SchemeSymbol(str):
    """An unquoted Scheme symbol; distinct from a string literal."""


class SchemeQuotedSymbol(str):
    """A quoted Scheme symbol such as 'guix."""


class SchemeString(str):
    """A Scheme string literal; distinct from an unquoted symbol."""


def tokenize(text: str) -> list[str]:
    """Tokenize the deliberately small Scheme subset used by channel locks."""
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
            buffer: list[str] = []
            terminated = False
            while end < len(text):
                current = text[end]
                if current == '"':
                    terminated = True
                    end += 1
                    break
                if current == "\\":
                    if end + 1 >= len(text):
                        raise ParseError("unterminated escape in string")
                    buffer.append(text[end + 1])
                    end += 2
                    continue
                buffer.append(current)
                end += 1
            if not terminated:
                raise ParseError("unterminated string")
            tokens.append('"' + "".join(buffer) + '"')
            index = end
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
            if len(token) < 2 or not token.endswith('"'):
                raise ParseError("malformed string token")
            return SchemeString(token[1:-1]), position + 1
        if token == "#f":
            return False, position + 1
        if token.startswith("'"):
            if len(token) == 1:
                raise ParseError("empty quoted symbol")
            return SchemeQuotedSymbol(token[1:]), position + 1
        return SchemeSymbol(token), position + 1

    value, position = read(0)
    if position != len(tokens):
        raise ParseError("trailing tokens after the first form")
    return value


def channels_of(form: Any) -> list[dict[str, Any]]:
    """Read channel records, rejecting duplicate and unknown fields."""
    if not isinstance(form, list) or not form or not isinstance(form[0], SchemeSymbol) or form[0] != "list":
        raise ParseError("expected (list (channel ...) ...)")

    found: list[dict[str, Any]] = []
    for entry in form[1:]:
        if not isinstance(entry, list) or not entry or not isinstance(entry[0], SchemeSymbol) or entry[0] != "channel":
            raise ParseError(f"unexpected entry: {entry!r}")
        channel: dict[str, Any] = {}
        for field in entry[1:]:
            if not isinstance(field, list) or not field:
                raise ParseError(f"malformed channel field: {field!r}")
            key = field[0]
            if not isinstance(key, SchemeSymbol) or key not in REQUIRED_FIELDS:
                raise ParseError(f"unexpected channel field: {key!r}")
            if key in channel:
                raise ParseError(f"duplicate channel field: {key!r}")
            if len(field) != 2:
                raise ParseError(f"channel field {key!r} must have exactly one value")
            value = field[1]
            if key == "name":
                if not isinstance(value, SchemeQuotedSymbol):
                    raise ParseError("channel name must be a quoted symbol")
                value = str(value)
            elif key in {"url", "commit"}:
                if not isinstance(value, SchemeString):
                    raise ParseError(f"channel field {key!r} must be a Scheme string")
                value = str(value)
            elif key == "branch":
                if value is not False:
                    raise ParseError("channel branch must be the Scheme boolean #f")
            channel[key] = value
        missing = REQUIRED_FIELDS - channel.keys()
        if missing:
            raise ParseError(f"channel is missing required fields: {sorted(missing)}")
        found.append(channel)
    return found


def _introduction_is_canonical(value: Any) -> bool:
    """Check the known Guix trust-root metadata shape, not its signature."""
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not isinstance(value[0], SchemeSymbol)
        or value[0] != "make-channel-introduction"
    ):
        return False
    commit, fingerprint_form = value[1], value[2]
    if not isinstance(commit, SchemeString) or not COMMIT.fullmatch(commit):
        return False
    if commit != INTRODUCTION_COMMIT:
        return False
    if (
        not isinstance(fingerprint_form, list)
        or len(fingerprint_form) != 2
        or not isinstance(fingerprint_form[0], SchemeSymbol)
        or fingerprint_form[0] != "openpgp-fingerprint"
        or not isinstance(fingerprint_form[1], SchemeString)
    ):
        return False
    fingerprint = re.sub(r"\s+", "", fingerprint_form[1]).upper()
    return bool(FINGERPRINT.fullmatch(fingerprint) and fingerprint == INTRODUCTION_FINGERPRINT)


def check(text: str) -> list[str]:
    """Return structural policy violations. Empty does not mean signatures verified."""
    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    problems: list[str] = []
    if len(channels) != 1:
        problems.append(
            f"the Free lock must contain exactly one channel; found {len(channels)}"
        )

    for channel in channels:
        name = channel["name"]
        if name not in ALLOWED_CHANNELS:
            problems.append(
                f"channel {name!r} is not an official Guix channel; a third-party "
                "channel replaces packages and is code execution"
            )

        url = channel["url"]
        if not isinstance(url, str) or url not in ALLOWED_REPOSITORIES:
            problems.append(
                f"channel {name!r} does not use an exact allow-listed official repository URL: {url!r}"
            )
        else:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port is not None
                or parsed.query
                or parsed.fragment
            ):
                problems.append(f"channel {name!r} URL contains unsupported components")

        if channel["branch"] is not False:
            problems.append(
                f"channel {name!r} must use branch #f and a fixed commit, not a moving branch"
            )

        commit = channel["commit"]
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            problems.append(
                f"channel {name!r} is not pinned to a full lowercase commit hash: {commit!r}"
            )

        if not _introduction_is_canonical(channel["introduction"]):
            problems.append(
                f"channel {name!r} does not declare the canonical Guix introduction commit and full OpenPGP fingerprint"
            )

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description=(
            "Check the structural Free-only policy of channels.lock.scm. "
            "Cryptographic authentication is verified by Guix, not this script."
        ),
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = args.lock.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-channels: cannot read {args.lock}: {exc}", file=sys.stderr)
        return 2

    problems = check(text)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {args.lock.name} passes structural Free-only policy; "
        "cryptographic authentication remains a Guix verification step"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
