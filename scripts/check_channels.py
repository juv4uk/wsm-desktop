# SPDX-License-Identifier: LicenseRef-Volnist
"""Структурно перевіряє окремі Free та Compatibility Guix channel locks.

Цей checker НЕ перевіряє криптографічний підпис. Автентифікацію виконує
Guix time-machine з увімкненою перевіркою channel authentication.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_LOCKS = {
    "free": ROOT / "channels.lock.scm",
    "compatibility": ROOT / "channels.compatibility.lock.scm",
}
POLICIES = {
    "free": {
        "channels": {"guix"},
        "urls": {
            "guix": {
                "https://git.guix.gnu.org/guix.git",
                "https://git.savannah.gnu.org/git/guix.git",
            }
        },
    },
    "compatibility": {
        "channels": {"guix", "nonguix"},
        "urls": {
            "guix": {
                "https://git.guix.gnu.org/guix.git",
                "https://git.savannah.gnu.org/git/guix.git",
            },
            "nonguix": {"https://gitlab.com/nonguix/nonguix"},
        },
    },
}
DEFAULT_POLICY = "free"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
GUIX_INTRODUCTION_COMMIT = "9edb3f66fd807b096b48283debdcddccfea34bad"
GUIX_INTRODUCTION_FINGERPRINT = "BBB02DDF2CEAF6A80D1DE643A2A06DF2A33A54FA"
NONGUIX_INTRODUCTION_COMMIT = "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
NONGUIX_INTRODUCTION_FINGERPRINT = "2A393FFF68F4EF7A3D2912AF6F5120A022FBB2D5"
REQUIRED_FIELDS = {"name", "url", "branch", "commit", "introduction"}


class ParseError(Exception):
    """Помилка вузького Scheme-підмножини channel lock."""


class SchemeSymbol(str):
    """Неекранований Scheme symbol."""


class SchemeQuotedSymbol(str):
    """Scheme quoted symbol, наприклад 'guix."""


class SchemeString(str):
    """Scheme string literal."""


def tokenize(text: str) -> list[str]:
    """Токенізує Scheme lock і відхиляє незакриті рядки."""
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
    """Читає одне Scheme-вираження зі збереженням типів символів і рядків."""
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
    """Перетворює форму lock на записи, відхиляючи дублікати й невідомі поля."""
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


def _introduction_problems(name: str, value: Any) -> list[str]:
    """Перевіряє форму introduction; не виконує GPG/channel authentication."""
    prefix = f"channel {name!r} introduction"
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not isinstance(value[0], SchemeSymbol)
        or value[0] != "make-channel-introduction"
    ):
        return [f"{prefix} has an invalid make-channel-introduction form"]

    commit, fingerprint_form = value[1], value[2]
    if not isinstance(commit, SchemeString) or not COMMIT.fullmatch(commit):
        return [f"{prefix} must contain a full lowercase introduction commit"]

    if (
        not isinstance(fingerprint_form, list)
        or len(fingerprint_form) != 2
        or not isinstance(fingerprint_form[0], SchemeSymbol)
        or fingerprint_form[0] != "openpgp-fingerprint"
        or not isinstance(fingerprint_form[1], SchemeString)
    ):
        return [f"{prefix} must contain an OpenPGP fingerprint string"]

    fingerprint = re.sub(r"\s+", "", fingerprint_form[1]).upper()
    if not FINGERPRINT.fullmatch(fingerprint):
        return [f"{prefix} must contain a full 40-hex-character fingerprint"]

    if name == "guix" and (
        commit != GUIX_INTRODUCTION_COMMIT
        or fingerprint != GUIX_INTRODUCTION_FINGERPRINT
    ):
        return [f"{prefix} does not match the canonical GNU Guix trust root"]
    if name == "nonguix" and (
        commit != NONGUIX_INTRODUCTION_COMMIT
        or fingerprint != NONGUIX_INTRODUCTION_FINGERPRINT
    ):
        return [f"{prefix} does not match the canonical Nonguix trust root"]
    return []


def check(text: str, policy: str = DEFAULT_POLICY) -> list[str]:
    """Повертає structural policy violations; порожній список не є GPG PASS."""
    rules = POLICIES.get(policy)
    if rules is None:
        return [f"unknown policy {policy!r}; choose one of {sorted(POLICIES)}"]

    try:
        channels = channels_of(parse(tokenize(text)))
    except ParseError as exc:
        return [f"cannot parse the channel lock: {exc}"]

    problems: list[str] = []
    expected = rules["channels"]
    names = [channel["name"] for channel in channels]
    if len(channels) != len(expected) or set(names) != expected or len(names) != len(set(names)):
        problems.append(
            f"the {policy} lock must contain exactly one entry for each of "
            f"{sorted(expected)}; found {names!r}"
        )

    for channel in channels:
        name = channel["name"]
        if name not in expected:
            problems.append(f"channel {name!r} is not permitted by the {policy} policy")
            continue

        allowed_urls = rules["urls"][name]
        if channel["url"] not in allowed_urls:
            problems.append(
                f"channel {name!r} does not use an exact allow-listed repository URL: "
                f"{channel['url']!r}"
            )

        commit = channel["commit"]
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            problems.append(
                f"channel {name!r} is not pinned to a full lowercase commit hash: {commit!r}"
            )

        problems.extend(_introduction_problems(name, channel["introduction"]))

    return problems


def default_lock(policy: str) -> Path:
    """Повертає lock, що належить вибраній продуктовій політиці."""
    try:
        return POLICY_LOCKS[policy]
    except KeyError as exc:
        raise ValueError(f"unknown policy {policy!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-channels",
        description=(
            "Check the structural Free or Compatibility channel-lock policy. "
            "Cryptographic channel authentication must be verified by Guix."
        ),
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="lock file; defaults to the file owned by the selected policy",
    )
    parser.add_argument(
        "--policy",
        choices=sorted(POLICIES),
        default=DEFAULT_POLICY,
        help="free: GNU Guix only; compatibility: GNU Guix plus explicitly pinned Nonguix",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lock_path = args.lock or default_lock(args.policy)
    try:
        text = lock_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"check-channels: cannot read {lock_path} for {args.policy} policy: {exc}",
            file=sys.stderr,
        )
        return 2

    problems = check(text, args.policy)
    if problems:
        for problem in problems:
            print(f"check-channels: {problem}", file=sys.stderr)
        return 1

    print(
        f"check-channels: {lock_path.name} satisfies the structural {args.policy} policy; "
        "cryptographic authentication is NOT verified by this checker "
        "(use guix time-machine with authentication enabled)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
