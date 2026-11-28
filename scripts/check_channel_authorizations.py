# SPDX-License-Identifier: LicenseRef-Volnist
"""Check channel authorizations before the owner signs an introduction.

This is a local consistency preflight, not channel authentication. It parses
only actual version-0 authorization entries; fingerprints in comments or
unrelated strings are never considered authorized keys.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_channels import (  # noqa: E402
    ParseError as SchemeParseError,
    SchemeString,
    SchemeSymbol,
    parse as parse_scheme,
    tokenize as tokenize_scheme,
)

PLACEHOLDER = re.compile(r"FULL OPENPGP FINGERPRINT|YOUR FINGERPRINT|FPR", re.IGNORECASE)
FINGERPRINT_HEX = re.compile(r"^[0-9A-F]{40}$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fingerprints_in_authorizations(text: str) -> list[str]:
    """Return keys only from the first string of actual authorization entries.

    Guix format:
      (authorizations (version 0)
        (("FULL FINGERPRINT" (name "owner")) ...))
    """
    form = parse_scheme(tokenize_scheme(text))
    if (
        not isinstance(form, list)
        or len(form) != 3
        or not isinstance(form[0], SchemeSymbol)
        or form[0] != "authorizations"
    ):
        raise SchemeParseError("expected one authorizations form with three elements")

    version = form[1]
    if (
        not isinstance(version, list)
        or len(version) != 2
        or not isinstance(version[0], SchemeSymbol)
        or version[0] != "version"
        or not isinstance(version[1], SchemeSymbol)
        or version[1] != "0"
    ):
        raise SchemeParseError("expected (version 0)")

    entries = form[2]
    if not isinstance(entries, list):
        raise SchemeParseError("authorization entries must be a list")

    fingerprints: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, list) or not entry:
            raise SchemeParseError(f"authorization entry {index} must be a non-empty list")

        key = entry[0]
        if not isinstance(key, SchemeString):
            raise SchemeParseError(f"authorization entry {index} fingerprint must be a string")

        raw = str(key)
        if PLACEHOLDER.search(raw):
            raise SchemeParseError(f"authorization entry {index} still contains a placeholder")

        compact = re.sub(r"\s+", "", raw).upper()
        if not FINGERPRINT_HEX.fullmatch(compact):
            raise SchemeParseError(
                f"authorization entry {index} is not a full 40-hex fingerprint"
            )

        spaced = " ".join(compact[offset : offset + 4] for offset in range(0, 40, 4))
        if spaced in seen:
            raise SchemeParseError(f"authorization entry {index} duplicates fingerprint {spaced}")
        seen.add(spaced)
        fingerprints.append(spaced)

        for metadata in entry[1:]:
            if (
                not isinstance(metadata, list)
                or len(metadata) != 2
                or not isinstance(metadata[0], SchemeSymbol)
            ):
                raise SchemeParseError(
                    f"authorization entry {index} has malformed optional metadata"
                )

    return fingerprints


def public_key_files(root: Path) -> list[Path]:
    """Find public keyring files without following symlinks."""
    return sorted(root.rglob("*.key"))


def key_file_fingerprints(root: Path) -> dict[str, str]:
    """Verify each public .key file with GnuPG; missing tools and invalid files fail closed."""
    files = public_key_files(root)
    if not files:
        return {}
    if shutil.which("gpg") is None:
        raise RuntimeError("gpg is unavailable; public .key files cannot be verified")

    found: dict[str, str] = {}
    for key_file in files:
        if key_file.is_symlink() or not key_file.is_file():
            raise RuntimeError(f"{key_file.name} is not a regular public-key file")

        completed = subprocess.run(
            ["gpg", "--show-keys", "--with-colons", str(key_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"gpg --show-keys failed for {key_file.name}")

        fingerprints: list[str] = []
        for line in completed.stdout.splitlines():
            if line.startswith("fpr:"):
                fields = line.split(":")
                if len(fields) > 9 and FINGERPRINT_HEX.fullmatch(fields[9].upper()):
                    fingerprints.append(fields[9].upper())
        if not fingerprints:
            raise RuntimeError(f"gpg found no valid full fingerprint in {key_file.name}")

        found[key_file.name] = fingerprints[0]

    return found


def problems(root: Path, require_bootstrapped: bool = False) -> list[str]:
    """Return reasons the authorization files are not locally consistent."""
    authorizations = root / ".guix-authorizations"
    if not authorizations.is_file():
        if require_bootstrapped:
            return [
                ".guix-authorizations is absent: the channel is not bootstrapped "
                "(see docs/GUIX-CHANNEL.md, bootstrap step 2)"
            ]
        return []

    try:
        listed = fingerprints_in_authorizations(read(authorizations))
    except (OSError, SchemeParseError) as exc:
        return [f".guix-authorizations is invalid: {exc}"]

    found: list[str] = []
    if not listed:
        found.append(".guix-authorizations lists no full OpenPGP fingerprint")

    try:
        keys = key_file_fingerprints(root)
    except (OSError, RuntimeError) as exc:
        return found + [f"public-key verification cannot be completed: {exc}"]

    for name, fingerprint in keys.items():
        spaced = " ".join(fingerprint[i : i + 4] for i in range(0, 40, 4))
        if spaced not in listed:
            found.append(
                f"{name} holds key {spaced} which is not listed in .guix-authorizations"
            )

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check channel authorizations before the owner signs an introduction."
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument(
        "--require-bootstrapped",
        action="store_true",
        help="fail when .guix-authorizations is absent (use after the bootstrap)",
    )
    arguments = parser.parse_args(argv)

    root = Path(arguments.root)
    found = problems(root, require_bootstrapped=arguments.require_bootstrapped)
    if found:
        print("\n".join(f"channel-authorizations: {item}" for item in found), file=sys.stderr)
        return 1

    if not (root / ".guix-authorizations").is_file():
        print(
            "channel-authorizations: not bootstrapped yet — no authorizations to check. "
            "Authentication is proven only by the Guix authentication command "
            "on a signed history."
        )
        return 0

    if not public_key_files(root):
        print(
            "channel-authorizations: authorization form is valid; "
            "KEY_FILE_CHECK=NOT_RUN (no public .key files in this checkout). "
            "This is not authentication; the Guix authentication command on a "
            "signed history is required."
        )
        return 0

    print(
        "channel-authorizations: local authorization and public-key files are consistent. "
        "This is not authentication; the Guix authentication command on the signed "
        "introduction history is still required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
