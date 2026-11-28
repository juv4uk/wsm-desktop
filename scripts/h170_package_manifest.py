# SPDX-License-Identifier: LicenseRef-Volnist
"""Print the package set of an H170 publication manifest, one name per line.

`.github/workflows/package-archives.yml` used to take a space-separated list of
package names typed by hand into the dispatch form. A list typed into a form is
impossible to review before it ships and impossible to compare with what the
machine actually needs.

The manifest file is the reviewable source; this script is the bridge. It reads
the manifest and prints exactly the names the workflow loops over, so the
workflow never has to parse Scheme with `sed` and the extraction can be tested
without Guix:

    python3 scripts/h170_package_manifest.py \\
        drivers/profiles/h170-publication-packages.scm

The script deliberately does not evaluate Scheme. It reads the string literals
of the single `specifications->manifest` form, because that is all the workflow
needs; whether the names resolve to real packages is a question only `guix` can
answer, and that happens in the build step, not here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MANIFEST_FORM = "specifications->manifest"
# The same character set the workflow accepts in a build step. Kept here as well
# so a name can never pass this reader and then be refused by the shell case.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9._+-]+$")
STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


class ManifestError(Exception):
    """The manifest cannot be read as a package set."""


def strip_comments(text: str) -> str:
    """Drop `;` comments and `#| |#` blocks without touching string contents."""
    out: list[str] = []
    index = 0
    length = len(text)
    in_string = False
    block_depth = 0

    while index < length:
        character = text[index]

        if in_string:
            out.append(character)
            if character == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            if character == '"':
                in_string = False
            index += 1
            continue

        if block_depth:
            if text.startswith("#|", index):
                block_depth += 1
                index += 2
                continue
            if text.startswith("|#", index):
                block_depth -= 1
                index += 2
                continue
            if character == "\n":
                out.append(character)
            index += 1
            continue

        if text.startswith("#|", index):
            block_depth = 1
            index += 2
            continue
        if character == '"':
            in_string = True
            out.append(character)
            index += 1
            continue
        if character == ";":
            while index < length and text[index] != "\n":
                index += 1
            continue
        out.append(character)
        index += 1

    if in_string:
        raise ManifestError("unterminated string literal")
    if block_depth:
        raise ManifestError("unterminated #| block comment")
    return "".join(out)


def package_names(text: str) -> list[str]:
    """The package names a manifest declares, in order, without duplicates."""
    code = strip_comments(text)
    position = code.find(f"({MANIFEST_FORM}")
    if position < 0:
        raise ManifestError(f"no ({MANIFEST_FORM} ...) form in the manifest")

    # Everything from the form head to the closing paren of its argument. The
    # manifest is a flat list of strings, so the last ')' of the file closes it.
    body = code[position + len(MANIFEST_FORM) + 1 :]
    names = STRING_LITERAL.findall(body)

    if not names:
        raise ManifestError(f"({MANIFEST_FORM} ...) lists no package names")

    seen: set[str] = set()
    for name in names:
        if not NAME_PATTERN.match(name):
            raise ManifestError(
                f"refusing odd package name {name!r}: only A-Z a-z 0-9 . _ + - "
                "are allowed"
            )
        if name in seen:
            raise ManifestError(f"duplicate package name {name!r}")
        seen.add(name)
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the package set of an H170 publication manifest."
    )
    parser.add_argument("manifest", type=Path, help="path to the manifest .scm file")
    parser.add_argument(
        "--json", action="store_true", help="print a JSON array instead of lines"
    )
    arguments = parser.parse_args(argv)

    try:
        text = arguments.manifest.read_text(encoding="utf-8")
        names = package_names(text)
    except OSError as error:
        print(f"cannot read manifest: {error}", file=sys.stderr)
        return 2
    except ManifestError as error:
        print(f"{arguments.manifest}: {error}", file=sys.stderr)
        return 2

    if arguments.json:
        print(json.dumps(names, ensure_ascii=False))
    else:
        for name in names:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
