# SPDX-License-Identifier: LicenseRef-Volnist
"""Check the structural policy of WSM's separate Guix channel locks.

This is deliberately NOT a cryptographic signature verifier. It validates the
small Scheme data contract and exact repository identities so that a lock cannot
quietly add, rename, duplicate, or redirect a channel. Real channel authentication
must still be performed by GNU Guix with authentication enabled.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FREE_LOCK = ROOT / "channels.lock.scm"
COMPATIBILITY_LOCK = ROOT / "channels.compatibility.lock.scm"
DEFAULT_LOCKS = {
    "free": FREE_LOCK,
    "compatibility": COMPATIBILITY_LOCK,
}

# Exact identities, not host allow-lists. A repository hosted on gitlab.com is
# not automatically Nonguix; changing the path changes the code being trusted.
ALLOWED_REPOSITORIES = {
    "guix": {
        "https://git.guix.gnu.org/guix.git",
        "https://git.savannah.gnu.org/git/guix.git",
    },
    "nonguix": {
        "https://gitlab.com/nonguix/nonguix",
    },
}
POLICIES = {
    "free": ("guix",),
    "compatibility": ("guix", "nonguix"),
}
REQUIRED_FIELDS = {"name", "url", "branch", "commit", "introduction"}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
INTRODUCTIONS = {
    "guix": {
        "commit": "9edb3f66fd807b096b48283debdcddccfea34bad",
        "fingerprint": "BBB02DDF2CEAF6A80D1DE643A2A06DF2A33A54FA",
    },
    "nonguix": {
        "commit": "897c1a470da759236cc11798f4e0a5f7d4d59fbc",
        "fingerprint": "2A393FFF68F4EF7A3D2912AF6F5120A022FBB2D5",
    },
}


class ParseError(Exception):
    """The lock is outside the intentionally small supported Scheme subset."""


class SchemeSymbol(str):
    """An unquoted Scheme symbol."""


class SchemeQuotedSymbol(str):
    """A quoted Scheme symbol such as 'guix."""


class SchemeString(str):
    """A Scheme string literal, distinct from a symbol."""


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
    """Parse one Scheme datum, preserving strings, quoted symbols and #f."""
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
            elif key == "branch":
                if value is not False:
                    raise ParseError("channel branch must be the Scheme boolean #f")
            elif key == "introduction":
                if not isinstance(value, list):
                    raise ParseError("channel introduction must be a Scheme form")
            channel[key] = value

        missing = REQUIRED_FIELDS - channel.keys()
        if missing:
            raise ParseError(f"channel is missing required fields: {sorted(missing)}")
        found.append(channel)
    return found


def _introduction_is_canonical(value: Any, channel_name: str) -> bool:
    """Check the known upstream trust-root metadata shape, not its signature."""
    expected = INTRODUCTIONS[channel_name]
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
    if str(commit) != expected["commit"]:
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
    return bool(FINGERPRINT.fullmatch(fingerprint) and fingerprint == expected["fingerprint"])


def check(text: str, policy: str = "free") -> list[str]:
    """Return structural policy violations; an empty list is not GPG proof."""
    if policy not in POLICIES:
        return [f"unknown policy {policy!r}; choose one of {sorted(POLICIES)}"]

    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    expected_names = POLICIES[policy]
    actual_names = [channel["name"] for channel in channels]
    problems: list[str] = []

    if len(channels) != len(expected_names):
        problems.append(
            f"the {policy} lock must contain exactly {len(expected_names)} channel(s); "
            f"found {len(channels)}"
        )
    if len(set(actual_names)) != len(actual_names):
        problems.append("the lock contains duplicate channel names")
    if set(actual_names) != set(expected_names):
        problems.append(
            f"the {policy} lock must contain exactly these channel names: "
            f"{', '.join(expected_names)}"
        )

    for channel in channels:
        name = channel["name"]
        if name not in expected_names:
            problems.append(
                f"channel {name!r} is not permitted by the {policy} policy"
            )
            continue

        url = channel["url"]
        if not isinstance(url, str) or url not in ALLOWED_REPOSITORIES[name]:
            problems.append(
                f"channel {name!r} does not use an exact allow-listed repository URL: {url!r}"
            )

        commit = channel["commit"]
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            problems.append(
                f"channel {name!r} is not pinned to a full lowercase commit hash: {commit!r}"
            )

        if channel["branch"] is not False:
            problems.append(
                f"channel {name!r} must use branch #f and a fixed commit"
            )

        if not _introduction_is_canonical(channel["introduction"], name):
            problems.append(
                f"channel {name!r} does not declare its canonical introduction "
                "commit and full OpenPGP fingerprint"
            )

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description=(
            "Check the structural policy of WSM channel locks. "
            "Cryptographic authentication is verified by Guix, not this script."
        ),
    )
    parser.add_argument("--policy", choices=sorted(POLICIES), default="free")
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="lock file (defaults to the lock associated with --policy)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lock = args.lock or DEFAULT_LOCKS[args.policy]
    try:
        text = lock.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-channels: cannot read {lock}: {exc}", file=sys.stderr)
        return 2

    problems = check(text, args.policy)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {lock.name} satisfies the {args.policy} structural policy; "
        "Guix must still perform cryptographic channel authentication"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
