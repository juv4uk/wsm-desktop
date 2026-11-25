# SPDX-License-Identifier: LicenseRef-Volnist
"""Structural policy checks for WSM's separate Free and Compatibility locks.

This module validates lock structure, repository identity, pins and channel
introduction metadata. It does NOT cryptographically verify Git signatures.
Actual authentication must be performed by Guix with authentication enabled.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")

GUIX_INTRODUCTION_COMMIT = "9edb3f66fd807b096b48283debdcddccfea34bad"
GUIX_INTRODUCTION_FINGERPRINT = "BBB02DDF2CEAF6A80D1DE643A2A06DF2A33A54FA"
NONGUIX_INTRODUCTION_COMMIT = "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
NONGUIX_INTRODUCTION_FINGERPRINT = "2A393FFF68F4EF7A3D2912AF6F5120A022FBB2D5"

GUIX_URLS = {
    "https://git.guix.gnu.org/guix.git",
    "https://git.savannah.gnu.org/git/guix.git",
}
NONGUIX_URLS = {"https://gitlab.com/nonguix/nonguix"}

# Each product has a separate lock. The Compatibility policy explicitly allows
# only the named Nonguix repository; it does not allow arbitrary third-party
# channels or a second copy of either channel.
POLICIES: dict[str, dict[str, Any]] = {
    "free": {
        "channel_names": ("guix",),
        "repositories": {"guix": GUIX_URLS},
        "introductions": {
            "guix": (GUIX_INTRODUCTION_COMMIT, GUIX_INTRODUCTION_FINGERPRINT)
        },
    },
    "compatibility": {
        "channel_names": ("guix", "nonguix"),
        "repositories": {
            "guix": GUIX_URLS,
            "nonguix": NONGUIX_URLS,
        },
        "introductions": {
            "guix": (GUIX_INTRODUCTION_COMMIT, GUIX_INTRODUCTION_FINGERPRINT),
            "nonguix": (
                NONGUIX_INTRODUCTION_COMMIT,
                NONGUIX_INTRODUCTION_FINGERPRINT,
            ),
        },
    },
}
DEFAULT_POLICY = "free"
DEFAULT_LOCKS = {
    "free": ROOT / "channels.lock.scm",
    "compatibility": ROOT / "channels.compatibility.lock.scm",
}
REQUIRED_FIELDS = {"name", "url", "branch", "commit", "introduction"}


class ParseError(Exception):
    """The input is outside the deliberately small lock-file Scheme subset."""


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
            items: list[Any] = []
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
    if (
        not isinstance(form, list)
        or not form
        or not isinstance(form[0], SchemeSymbol)
        or form[0] != "list"
    ):
        raise ParseError("expected (list (channel ...) ...)")

    found: list[dict[str, Any]] = []
    for entry in form[1:]:
        if (
            not isinstance(entry, list)
            or not entry
            or not isinstance(entry[0], SchemeSymbol)
            or entry[0] != "channel"
        ):
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
            elif key == "branch" and value is not False:
                raise ParseError("channel branch must be the Scheme boolean #f")
            channel[key] = value
        missing = REQUIRED_FIELDS - channel.keys()
        if missing:
            raise ParseError(f"channel is missing required fields: {sorted(missing)}")
        found.append(channel)
    return found


def _introduction_matches(value: Any, expected: tuple[str, str]) -> bool:
    """Check canonical trust-root metadata, not the channel's Git signature."""
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not isinstance(value[0], SchemeSymbol)
        or value[0] != "make-channel-introduction"
    ):
        return False
    commit, fingerprint_form = value[1], value[2]
    expected_commit, expected_fingerprint = expected
    if (
        not isinstance(commit, SchemeString)
        or not COMMIT.fullmatch(commit)
        or str(commit) != expected_commit
    ):
        return False
    if (
        not isinstance(fingerprint_form, list)
        or len(fingerprint_form) != 2
        or not isinstance(fingerprint_form[0], SchemeSymbol)
        or fingerprint_form[0] != "openpgp-fingerprint"
        or not isinstance(fingerprint_form[1], SchemeString)
    ):
        return False
    fingerprint = re.sub(r"\s+", "", str(fingerprint_form[1])).upper()
    return bool(
        FINGERPRINT.fullmatch(fingerprint)
        and fingerprint == expected_fingerprint
    )


def default_lock_for(policy: str) -> Path:
    if policy not in DEFAULT_LOCKS:
        raise ValueError(f"unknown channel policy {policy!r}")
    return DEFAULT_LOCKS[policy]


def check(text: str, policy: str = DEFAULT_POLICY) -> list[str]:
    """Return structural policy violations; empty is not signature verification."""
    if policy not in POLICIES:
        return [f"unknown policy {policy!r}; choose one of {sorted(POLICIES)}"]
    rules = POLICIES[policy]
    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    problems: list[str] = []
    expected_names = rules["channel_names"]
    actual_names = tuple(channel["name"] for channel in channels)
    if actual_names != expected_names:
        problems.append(
            f"the {policy} lock must declare channels in this exact order "
            f"{expected_names!r}; found {actual_names!r}"
        )

    for channel in channels:
        name = channel["name"]
        allowed_urls = rules["repositories"].get(name)
        if allowed_urls is None:
            problems.append(f"channel {name!r} is not allowed by the {policy} policy")
        elif channel["url"] not in allowed_urls:
            problems.append(
                f"channel {name!r} does not use an exact allow-listed repository URL: "
                f"{channel['url']!r}"
            )
        else:
            parsed_url = urlsplit(channel["url"])
            if (
                parsed_url.scheme != "https"
                or not parsed_url.netloc
                or parsed_url.username is not None
                or parsed_url.password is not None
                or parsed_url.port is not None
                or parsed_url.query
                or parsed_url.fragment
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

        expected_introduction = rules["introductions"].get(name)
        if expected_introduction is None or not _introduction_matches(
            channel["introduction"], expected_introduction
        ):
            problems.append(
                f"channel {name!r} does not declare the canonical introduction commit "
                "and full OpenPGP fingerprint for this policy"
            )

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description=(
            "Check the structural Free/Compatibility channel policy. "
            "Cryptographic authentication is verified by Guix, not this script."
        ),
    )
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default=DEFAULT_POLICY,
        help="free: official Guix only; compatibility: Guix plus exactly the named Nonguix channel",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="lock file; defaults to channels.lock.scm for free or channels.compatibility.lock.scm for compatibility",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lock_path = args.lock if args.lock is not None else default_lock_for(args.policy)
    try:
        text = lock_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-channels: cannot read {lock_path}: {exc}", file=sys.stderr)
        return 2

    problems = check(text, args.policy)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {lock_path.name} satisfies the {args.policy} structural policy; "
        "cryptographic authentication remains a Guix verification step"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
