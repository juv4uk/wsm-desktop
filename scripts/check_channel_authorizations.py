# SPDX-License-Identifier: LicenseRef-Volnist
"""Check channel authorizations before the owner signs an introduction.

This is a local consistency preflight, not a Guix authentication implementation.
It parses the small S-expression grammar used by .guix-authorizations and can
compare it with an explicit local checkout of the channel keyring branch.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = re.compile(r"FULL OPENPGP FINGERPRINT|YOUR FINGERPRINT|FPR", re.IGNORECASE)
FULL_FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")


@dataclass(frozen=True)
class SchemeString:
    value: str


@dataclass(frozen=True)
class SchemeSymbol:
    value: str


def parse_scheme_forms(text: str) -> list[object]:
    """Parse the list/string/symbol/integer subset used by authorizations."""
    index = 0
    length = len(text)

    def skip_space_and_comments() -> None:
        nonlocal index
        while index < length:
            if text[index].isspace():
                index += 1
                continue
            if text[index] == ";":
                newline = text.find("\n", index)
                index = length if newline < 0 else newline + 1
                continue
            if text.startswith("#|", index):
                index += 2
                depth = 1
                while index < length and depth:
                    if text.startswith("#|", index):
                        depth += 1
                        index += 2
                    elif text.startswith("|#", index):
                        depth -= 1
                        index += 2
                    else:
                        index += 1
                if depth:
                    raise ValueError("unterminated block comment")
                continue
            break

    def parse_one() -> object:
        nonlocal index
        skip_space_and_comments()
        if index >= length:
            raise ValueError("unexpected end of file")

        char = text[index]
        if char == "(":
            index += 1
            values: list[object] = []
            while True:
                skip_space_and_comments()
                if index >= length:
                    raise ValueError("unterminated list")
                if text[index] == ")":
                    index += 1
                    return values
                values.append(parse_one())

        if char == ")":
            raise ValueError("unexpected closing parenthesis")

        if char == '"':
            index += 1
            value: list[str] = []
            while index < length:
                char = text[index]
                index += 1
                if char == '"':
                    return SchemeString("".join(value))
                if char == "\\":
                    if index >= length:
                        raise ValueError("unterminated string escape")
                    escaped = text[index]
                    index += 1
                    mapping = {
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                        '"': '"',
                        "\\": "\\",
                    }
                    if escaped == "x":
                        end = text.find(";", index)
                        if end < 0:
                            raise ValueError("unterminated hexadecimal string escape")
                        try:
                            value.append(chr(int(text[index:end], 16)))
                        except ValueError as error:
                            raise ValueError("invalid hexadecimal string escape") from error
                        index = end + 1
                    elif escaped == "\n":
                        while index < length and text[index].isspace():
                            index += 1
                    else:
                        value.append(mapping.get(escaped, escaped))
                else:
                    value.append(char)
            raise ValueError("unterminated string")

        start = index
        while index < length:
            if text[index].isspace() or text[index] in "();":
                break
            if text.startswith("#|", index):
                break
            index += 1
        if start == index:
            raise ValueError(f"unsupported reader syntax at offset {index}")
        atom = text[start:index]
        if re.fullmatch(r"[+-]?[0-9]+", atom):
            return int(atom)
        return SchemeSymbol(atom)

    forms: list[object] = []
    while True:
        skip_space_and_comments()
        if index >= length:
            return forms
        forms.append(parse_one())


def parse_authorizations(text: str) -> list[str]:
    """Return normalized authorized fingerprints or reject the entire file."""
    forms = parse_scheme_forms(text)
    if len(forms) != 1:
        raise ValueError(f"expected exactly one top-level form, found {len(forms)}")

    root = forms[0]
    if (
        not isinstance(root, list)
        or len(root) != 3
        or root[0] != SchemeSymbol("authorizations")
    ):
        raise ValueError("expected (authorizations (version 0) (...))")

    version = root[1]
    if (
        not isinstance(version, list)
        or len(version) != 2
        or version[0] != SchemeSymbol("version")
        or isinstance(version[1], bool)
        or version[1] != 0
    ):
        actual = version[1] if isinstance(version, list) and len(version) > 1 else "missing"
        raise ValueError(f"authorization version is {actual!r}, expected 0")

    entries = root[2]
    if not isinstance(entries, list) or not entries:
        raise ValueError("authorization entries must be a non-empty list")

    parsed: list[str] = []
    seen: set[str] = set()
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, list) or not entry:
            raise ValueError(
                f"authorization entry {number} must begin with a fingerprint"
            )
        raw_fingerprint = entry[0]
        if not isinstance(raw_fingerprint, SchemeString):
            raise ValueError(f"authorization entry {number} fingerprint must be a string")

        compact = "".join(raw_fingerprint.value.split()).upper()
        if PLACEHOLDER.search(raw_fingerprint.value):
            raise ValueError(f"authorization entry {number} still contains a placeholder fingerprint")
        if not FULL_FINGERPRINT.fullmatch(compact):
            raise ValueError(
                f"authorization entry {number} has no full 40-hex OpenPGP fingerprint"
            )

        fingerprint = " ".join(compact[offset : offset + 4] for offset in range(0, 40, 4))
        if fingerprint in seen:
            raise ValueError(f"duplicate authorized fingerprint: {fingerprint}")
        seen.add(fingerprint)

        # Guix currently ignores these optional key/value pairs. Validate their
        # shape, but do not require a name or constrain future metadata values.
        for property_form in entry[1:]:
            if (
                not isinstance(property_form, list)
                or len(property_form) != 2
                or not isinstance(property_form[0], SchemeSymbol)
            ):
                raise ValueError(
                    f"authorization entry {number} contains malformed key/value metadata"
                )

        parsed.append(fingerprint)

    return parsed

def historical_authorization_fingerprints(root: Path, current_text: str) -> set[str]:
    """Collect every fingerprint ever authorized on this channel history through HEAD.

    Guix requires the keyring branch to retain public exports for historical
    authorization entries, including keys that are no longer in the current file.
    A shallow or unavailable Git history cannot prove that set and fails closed.
    """
    authorized = set(parse_authorizations(current_text))

    try:
        shallow = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-shallow-repository"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if shallow.returncode != 0:
            raise ValueError(
                "AUTH_HISTORY_CHECK=NOT_RUN: repository history is unavailable"
            )
        if shallow.stdout.strip().lower() == "true":
            raise ValueError(
                "AUTH_HISTORY_CHECK=NOT_RUN: shallow clone cannot prove historical key retention"
            )

        history = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%H", "HEAD", "--", ".guix-authorizations"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if history.returncode != 0:
            detail = history.stderr.strip() or f"exit status {history.returncode}"
            raise ValueError(f"AUTH_HISTORY_CHECK=NOT_RUN: git log failed: {detail}")

        for commit in filter(None, history.stdout.splitlines()):
            snapshot = subprocess.run(
                ["git", "-C", str(root), "show", f"{commit}:.guix-authorizations"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if snapshot.returncode != 0:
                detail = snapshot.stderr.strip() or f"exit status {snapshot.returncode}"
                raise ValueError(
                    f"AUTH_HISTORY_CHECK=NOT_RUN: cannot read authorization history at {commit}: {detail}"
                )
            authorized.update(parse_authorizations(snapshot.stdout))
    except subprocess.TimeoutExpired as error:
        raise ValueError("AUTH_HISTORY_CHECK=NOT_RUN: git history inspection timed out") from error
    except OSError as error:
        raise ValueError(f"AUTH_HISTORY_CHECK=NOT_RUN: cannot execute git: {error}") from error

    return authorized


def key_file_fingerprints(keyring_dir: Path) -> dict[str, str]:
    """Map primary fingerprints to .key file paths from the explicit keyring checkout."""
    if not keyring_dir.is_dir():
        raise ValueError(f"KEYRING_CHECK=NOT_RUN: keyring directory does not exist: {keyring_dir}")

    key_files = sorted(keyring_dir.rglob("*.key"))
    # An explicit, existing but empty keyring is a completed check with no
    # exports; the comparison below will report each missing authorized key.
    if not key_files:
        return {}
    if shutil.which("gpg") is None:
        raise ValueError("KEYRING_CHECK=NOT_RUN: gpg is unavailable")

    found: dict[str, str] = {}
    for key_file in key_files:
        if key_file.is_symlink() or not key_file.is_file():
            raise ValueError(f"invalid keyring entry is not a regular .key file: {key_file}")

        completed = subprocess.run(
            ["gpg", "--show-keys", "--with-colons", str(key_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit status {completed.returncode}"
            raise ValueError(f"cannot read public key {key_file}: {detail}")

        lines = completed.stdout.splitlines()
        primary_count = sum(line.startswith("pub:") for line in lines)
        fingerprints = [
            line.split(":")[9].upper()
            for line in lines
            if line.startswith("fpr:") and len(line.split(":")) > 9
        ]
        if primary_count != 1 or not fingerprints or not FULL_FINGERPRINT.fullmatch(fingerprints[0]):
            raise ValueError(
                f"{key_file} must contain exactly one primary public key with a full fingerprint"
            )

        compact = fingerprints[0]
        fingerprint = " ".join(compact[offset : offset + 4] for offset in range(0, 40, 4))
        if fingerprint in found:
            raise ValueError(
                f"duplicate public-key exports for {fingerprint}: {found[fingerprint]} and {key_file}"
            )
        found[fingerprint] = key_file.relative_to(keyring_dir).as_posix()

    return found


def problems(
    root: Path,
    keyring_dir: Path | None = None,
    require_bootstrapped: bool = False,
) -> list[str]:
    """Return reasons the authorizations/keyring are not locally consistent."""
    authorizations = root / ".guix-authorizations"
    if not authorizations.is_file():
        if require_bootstrapped:
            return [
                ".guix-authorizations is absent: the channel is not bootstrapped "
                "(see docs/GUIX-CHANNEL.md, bootstrap step 2)"
            ]
        return []

    try:
        current_authorizations = read(authorizations)
        authorized = historical_authorization_fingerprints(root, current_authorizations)
    except (OSError, UnicodeError, ValueError) as error:
        return [f".guix-authorizations/history is invalid: {error}"]

    if keyring_dir is None:
        return [
            "KEYRING_CHECK=NOT_RUN: supply --keyring-dir pointing to a local checkout "
            "of the channel keyring branch"
        ]

    try:
        keys = key_file_fingerprints(keyring_dir)
    except (OSError, ValueError) as error:
        return [str(error)]

    published = set(keys)
    found: list[str] = []

    for fingerprint in sorted(authorized - published):
        found.append(f"authorized fingerprint {fingerprint} has no public .key export in the keyring")
    for fingerprint in sorted(published - authorized):
        found.append(
            f"keyring file {keys[fingerprint]} exports unauthorized fingerprint {fingerprint}"
        )

    return found


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check channel authorizations against an explicit local keyring checkout."
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument(
        "--keyring-dir",
        type=Path,
        help="path to a local checkout of the channel keyring branch",
    )
    parser.add_argument(
        "--require-bootstrapped",
        action="store_true",
        help="fail when .guix-authorizations is absent (use after the bootstrap)",
    )
    arguments = parser.parse_args(argv)

    root = Path(arguments.root)
    found = problems(
        root,
        keyring_dir=arguments.keyring_dir,
        require_bootstrapped=arguments.require_bootstrapped,
    )
    if found:
        print("\n".join(f"channel-authorizations: {item}" for item in found), file=sys.stderr)
        return 1

    if not (root / ".guix-authorizations").is_file():
        print(
            "channel-authorizations: NOT_BOOTSTRAPPED; no authorization file to check. "
            "This does not mean the channel is authenticated."
        )
        return 0

    print(
        "channel-authorizations: local authorization and keyring files are consistent. "
        "This is not authentication; run guix git authenticate on the signed introduction."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
