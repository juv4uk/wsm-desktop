# SPDX-License-Identifier: LicenseRef-Volnist
"""Rewrite Guix narinfo URLs to immutable GitHub Release NAR assets.

For the pinned Guix 1.5 publish implementation, a gzip cache stores each NAR
as <cache>/gzip/<store-basename>.nar while the narinfo URL is
nar/gzip/<store-basename>. This tool flattens small narinfo files for a Pages
metadata site and points each URL at the matching Release asset named
<store-basename>.nar.

Only the URL value may change. All other bytes, including every field covered
by the Guix narinfo signature, are preserved exactly.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

URL_LINE = re.compile(
    r"^URL:(?P<before>\s*)(?P<value>\S+)(?P<after>\s*)$",
    re.MULTILINE,
)
COMPRESSION_LINE = re.compile(r"^Compression:\s*(\S+)\s*$", re.MULTILINE)
NAR_SUFFIX = ".nar"


def _url_value_span(text: str) -> tuple[int, int, str]:
    matches = list(URL_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one URL: field, found {len(matches)}"
        )
    match = matches[0]
    return match.start("value"), match.end("value"), match.group("value")


def _compression(text: str) -> str:
    matches = list(COMPRESSION_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one Compression: field, found {len(matches)}"
        )
    return matches[0].group(1)


def _without_url_value(text: str) -> str:
    start, end, _ = _url_value_span(text)
    return text[:start] + "<URL>" + text[end:]


def rewrite_url(text: str, base_url: str) -> str:
    """Point one Guix narinfo at its matching GitHub Release asset."""
    start, end, original = _url_value_span(text)
    compression = _compression(text)
    components = original.split("/")
    if (
        len(components) != 3
        or components[0] != "nar"
        or components[1] != compression
        or not components[2]
    ):
        raise ValueError(
            "narinfo URL must match Guix publish layout nar/<Compression>/<basename>"
        )

    basename = components[2]
    if basename in {".", ".."}:
        raise ValueError("narinfo URL has no usable NAR basename")

    target = f"{base_url.rstrip('/')}/{basename}{NAR_SUFFIX}"
    rewritten = text[:start] + target + text[end:]

    # Guard the whole document, not a hand-maintained subset of signed fields.
    if _without_url_value(text) != _without_url_value(rewritten):
        raise ValueError("rewriting URL changed narinfo content outside URL")
    return rewritten


def convert_directory(
    source: Path, destination: Path, base_url: str
) -> list[Path]:
    """Flatten nested Guix cache .narinfo files into DESTINATION."""
    narinfos = sorted(source.rglob("*.narinfo"))
    if not narinfos:
        raise ValueError(f"no .narinfo files found under {source}")

    rewritten: dict[str, str] = {}
    for narinfo in narinfos:
        content = narinfo.read_text(encoding="utf-8")
        converted = rewrite_url(content, base_url)
        name = narinfo.name
        previous = rewritten.get(name)
        if previous is not None and previous != converted:
            raise ValueError(f"conflicting duplicate narinfo basename: {name}")
        rewritten[name] = converted

    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in sorted(rewritten.items()):
        target = destination / name
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing file: {target}")
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="narinfo-to-release-urls",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--base-url",
        required=True,
        help="GitHub Release asset base URL, e.g. https://github.com/OWNER/REPO/releases/download/TAG",
    )
    args = parser.parse_args(argv)

    try:
        written = convert_directory(args.source, args.destination, args.base_url)
    except (OSError, ValueError) as exc:
        print(f"narinfo-to-release-urls: {exc}", file=sys.stderr)
        return 2
    print(f"narinfo-to-release-urls: rewrote {len(written)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
