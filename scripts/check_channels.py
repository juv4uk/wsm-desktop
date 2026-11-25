# SPDX-License-Identifier: LicenseRef-Volnist
"""Validate exact, pinned Guix channel sets for each WSM product image.

A hostname allowlist alone is not a trust policy: a different repository on
gitlab.com is different code. Each channel name is pinned to exact repository
URL and canonical upstream introduction values.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"^[0-9a-f]{40}$")

CHANNELS: dict[str, dict[str, Any]] = {
    "guix": {
        "urls": {
            "https://git.guix.gnu.org/guix.git",
            "https://git.savannah.gnu.org/git/guix.git",
        },
        "introduction_commit": "9edb3f66fd807b096b48283debdcddccfea34bad",
        "introduction_fingerprint": "BBB02DDF2CEAF6A80D1DE643A2A06DF2A33A54FA",
    },
    "nonguix": {
        "urls": {"https://gitlab.com/nonguix/nonguix"},
        "introduction_commit": "897c1a470da759236cc11798f4e0a5f7d4d59fbc",
        "introduction_fingerprint": "2A393FFF68F4EF7A3D2912AF6F5120A022FBB2D5",
    },
}

POLICIES: dict[str, tuple[str, ...]] = {
    "free": ("guix",),
    "compatibility": ("guix", "nonguix"),
}
DEFAULT_POLICY = "free"
DEFAULT_LOCKS = {
    "free": ROOT / "channels.lock.scm",
    "compatibility": ROOT / "channels.compatibility.lock.scm",
}


class ParseError(Exception):
    """The lock is not in the deliberately small, auditable Scheme subset."""


class SchemeString(str):
    """A quoted Scheme string, kept distinct from symbols."""


class SchemeSymbol(str):
    """A Scheme symbol, kept distinct from strings."""


def tokenize(text: str) -> list[str]:
    """Tokenize the small Scheme subset used by a Guix channel lock."""
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
            while end < len(text):
                current = text[end]
                if current == '"':
                    break
                if current == "\\":
                    if end + 1 >= len(text):
                        raise ParseError("unterminated escape in string")
                    escaped = text[end + 1]
                    if escaped not in {'"', "\\"}:
                        raise ParseError(f"unsupported string escape \\{escaped}")
                    buffer.append(escaped)
                    end += 2
                    continue
                buffer.append(current)
                end += 1
            if end >= len(text) or text[end] != '"':
                raise ParseError("unterminated string")
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
    """Parse one Scheme datum and reject trailing input."""
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
            return SchemeString(token[1:-1]), position + 1
        return SchemeSymbol(token), position + 1

    value, position = read(0)
    if position != len(tokens):
        raise ParseError("trailing tokens after the first form")
    return value


def _one_string(value: Any, field: str, channel: str) -> str:
    if not isinstance(value, SchemeString):
        raise ParseError(f"channel {channel!r} field {field!r} must be a quoted string")
    return str(value)


def _introduction(value: Any, channel: str) -> tuple[str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or value[0] != SchemeSymbol("make-channel-introduction")
        or not isinstance(value[2], list)
        or len(value[2]) != 2
        or value[2][0] != SchemeSymbol("openpgp-fingerprint")
    ):
        raise ParseError(
            f"channel {channel!r} introduction must be "
            "(make-channel-introduction COMMIT (openpgp-fingerprint FINGERPRINT))"
        )
    commit = _one_string(value[1], "introduction commit", channel)
    fingerprint = _one_string(value[2][1], "introduction fingerprint", channel)
    return commit, fingerprint


def channels_of(form: Any) -> list[dict[str, Any]]:
    """Parse a strict channel lock with no ignored or duplicate fields."""
    if (
        not isinstance(form, list)
        or not form
        or form[0] != SchemeSymbol("list")
    ):
        raise ParseError("expected (list (channel ...) ...)")

    found: list[dict[str, Any]] = []
    allowed_fields = {"name", "url", "branch", "commit", "introduction"}

    for entry in form[1:]:
        if (
            not isinstance(entry, list)
            or not entry
            or entry[0] != SchemeSymbol("channel")
        ):
            raise ParseError(f"unexpected lock entry: {entry!r}")

        fields: dict[str, Any] = {}
        for field in entry[1:]:
            if not isinstance(field, list) or not field:
                raise ParseError(f"malformed channel field: {field!r}")
            if not isinstance(field[0], SchemeSymbol):
                raise ParseError(f"channel field name is not a symbol: {field!r}")
            key = str(field[0])
            if key not in allowed_fields:
                raise ParseError(f"unknown channel field {key!r}")
            if key in fields:
                raise ParseError(f"duplicate channel field {key!r}")
            if len(field) != 2:
                raise ParseError(f"channel field {key!r} must have exactly one value")
            fields[key] = field[1]

        missing = allowed_fields - fields.keys()
        if missing:
            raise ParseError(f"channel is missing required fields: {sorted(missing)}")

        raw_name = fields["name"]
        if not isinstance(raw_name, SchemeSymbol) or not str(raw_name).startswith("'"):
            raise ParseError("channel name must be a quoted Scheme symbol")
        name = str(raw_name)[1:]
        if not name:
            raise ParseError("channel name must not be empty")

        url = _one_string(fields["url"], "url", name)
        branch = fields["branch"]
        if not isinstance(branch, SchemeSymbol):
            raise ParseError(f"channel {name!r} branch must be the Scheme symbol #f")
        commit = _one_string(fields["commit"], "commit", name)
        intro_commit, fingerprint = _introduction(fields["introduction"], name)

        found.append({
            "name": name,
            "url": url,
            "branch": str(branch),
            "commit": commit,
            "introduction_commit": intro_commit,
            "introduction_fingerprint": fingerprint,
        })

    return found


def check(text: str, policy: str = DEFAULT_POLICY) -> list[str]:
    """Return every reason a lock violates its exact product-channel policy."""
    if policy not in POLICIES:
        return [f"unknown policy {policy!r}; choose one of {sorted(POLICIES)}"]

    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    required_names = POLICIES[policy]
    expected = set(required_names)
    actual_names = [str(channel["name"]) for channel in channels]
    problems: list[str] = []

    if not channels:
        return ["the lock declares no channels"]

    duplicates = sorted({name for name in actual_names if actual_names.count(name) > 1})
    if duplicates:
        problems.append(f"duplicate channel names are not allowed: {duplicates}")

    actual = set(actual_names)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        problems.append(f"{policy} lock is missing required channels: {missing}")
    if unexpected:
        problems.append(f"{policy} lock has unexpected channels: {unexpected}")

    for channel in channels:
        name = channel["name"]
        spec = CHANNELS.get(name)
        if spec is None:
            continue

        if channel["url"] not in spec["urls"]:
            problems.append(
                f"channel {name!r} uses an unrecognized repository URL: {channel['url']!r}"
            )

        if channel["branch"] != "#f":
            problems.append(
                f"channel {name!r} must use branch #f with a pinned commit, "
                f"not {channel['branch']!r}"
            )

        commit = channel["commit"]
        if not COMMIT.fullmatch(commit):
            problems.append(
                f"channel {name!r} is not pinned to a full lowercase 40-character commit: {commit!r}"
            )

        intro_commit = channel["introduction_commit"]
        if (
            not COMMIT.fullmatch(intro_commit)
            or intro_commit != spec["introduction_commit"]
        ):
            problems.append(
                f"channel {name!r} does not use the canonical authenticated introduction commit"
            )

        fingerprint = re.sub(r"\s+", "", channel["introduction_fingerprint"]).upper()
        if fingerprint != spec["introduction_fingerprint"]:
            problems.append(
                f"channel {name!r} does not use the canonical OpenPGP introduction fingerprint"
            )

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description=(
            "Validate exact, pinned and authenticated channel repositories "
            "for the selected WSM product image."
        ),
    )
    parser.add_argument(
        "--lock",
        type=Path,
        help="explicit lock path; defaults to the lock belonging to --policy",
    )
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default=DEFAULT_POLICY,
        help=(
            "free: official Guix only (channels.lock.scm); "
            "compatibility: Guix plus exact Nonguix (channels.compatibility.lock.scm)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lock_path = args.lock or DEFAULT_LOCKS[args.policy]
    try:
        text = lock_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"check-channels: cannot read {lock_path}: {exc}", file=sys.stderr)
        return 2

    problems = check(text, args.policy)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {lock_path.name} satisfies the {args.policy} policy "
        "(exact repositories, pinned commits, canonical authenticated introductions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
