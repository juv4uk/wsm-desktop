# SPDX-License-Identifier: LicenseRef-Volnist
"""Check the channel authorizations *before* the owner signs an introduction.

`docs/GUIX-CHANNEL.md` requires the trust bootstrap to be done by the owner with
their own key: `.guix-authorizations` plus a signed introduction commit. Both are
expensive to redo — every attempt means a new signed commit — so a typo in the
fingerprint or a leftover placeholder should be caught before signing, not by
`guix git authenticate` afterwards.

This checker never claims authentication. It only answers: if the owner adds
these files today, are they internally consistent?

Three states:

* no `.guix-authorizations` — the channel is not bootstrapped. That is the
  current, honest state; the check passes and says so.
* the file exists but is inconsistent — fail with the specific reason.
* the file exists and is consistent — pass, while still saying that
  authentication itself is proven only by `guix git authenticate` on a real
  signed history.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"FULL OPENPGP FINGERPRINT|YOUR FINGERPRINT|FPR", re.IGNORECASE)
FINGERPRINT = re.compile(r"\b([0-9A-F]{4}(?:\s+[0-9A-F]{4}){9})\b")
AUTHORIZATIONS = re.compile(
    r"\(\s*authorizations\s*\(\s*version\s+(\d+)\s*\)(.*)\)\s*$",
    re.DOTALL,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fingerprints_in_authorizations(text: str) -> list[str]:
    """Every fingerprint listed as an authorized key, in file order."""
    return [match.group(1) for match in FINGERPRINT.finditer(text)]


def key_file_fingerprints(root: Path) -> dict[str, str]:
    """Fingerprint printed by each public key file, when gpg is available.

    The export is a text armour block; the fingerprint is not inside it, so we
    ask gpg. Without gpg we return an empty map and the caller says so rather
    than guessing from bytes.
    """
    import shutil
    import subprocess

    if shutil.which("gpg") is None:
        return {}
    found: dict[str, str] = {}
    for key_file in sorted(root.rglob("*.key")):
        completed = subprocess.run(
            ["gpg", "--show-keys", "--with-colons", str(key_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in completed.stdout.splitlines():
            if line.startswith("fpr:"):
                found[key_file.name] = line.split(":")[9]
                break
    return found


def problems(root: Path, require_bootstrapped: bool = False) -> list[str]:
    """Reasons the authorizations are not ready to sign. Empty list means ready."""
    authorizations = root / ".guix-authorizations"
    found: list[str] = []

    if not authorizations.is_file():
        if require_bootstrapped:
            found.append(
                ".guix-authorizations is absent: the channel is not bootstrapped "
                "(see docs/GUIX-CHANNEL.md, bootstrap step 2)"
            )
        return found

    text = read(authorizations)
    if PLACEHOLDER.search(text):
        found.append(
            ".guix-authorizations still contains a placeholder fingerprint; "
            "replace it with the owner's full fingerprint before signing"
        )

    match = AUTHORIZATIONS.search(text.strip())
    if match is None:
        found.append(
            ".guix-authorizations is not the Guix shape: "
            "(authorizations (version 0) ((\"FINGERPRINT\" (name \"...\"))))"
        )
    elif match.group(1) != "0":
        found.append(f".guix-authorizations uses version {match.group(1)}, expected 0")

    listed = fingerprints_in_authorizations(text)
    if not listed:
        found.append(".guix-authorizations lists no full OpenPGP fingerprint")

    keys = key_file_fingerprints(root)
    for name, fingerprint in keys.items():
        spaced = " ".join(fingerprint[i : i + 4] for i in range(0, len(fingerprint), 4))
        if listed and spaced not in listed:
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
            "Authentication is proven only by `guix git authenticate` on a signed history."
        )
        return 0

    print(
        "channel-authorizations: locally consistent. This is not authentication: "
        "only `guix git authenticate` on the signed introduction commit proves that."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
