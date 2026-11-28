# SPDX-License-Identifier: LicenseRef-Volnist
"""Rewrite only the URL in a signed Guix narinfo for static release hosting.

This tool does not create keys, sign narinfos, build NARs or publish cache data.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

URL_LINE = re.compile(r"^URL:[ \t]*(?P<value>\S+)[ \t]*$", re.MULTILINE)
SIGNATURE_LINE = re.compile(r"^Signature:[ \t]*(?P<value>\S+)[ \t]*$", re.MULTILINE)


def signed_prefix(text: str) -> str:
    """Return the exact signed prefix, ending at the sole Guix Signature line."""
    matches = list(SIGNATURE_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Guix Signature line, found {len(matches)}")
    return text[: matches[0].end()]


def rewrite_url(text: str, base_url: str, keep_path: bool = False) -> str:
    """Replace one post-signature URL value and preserve every other byte."""
    urls = list(URL_LINE.finditer(text))
    signatures = list(SIGNATURE_LINE.finditer(text))
    if len(urls) != 1:
        raise ValueError(f"expected exactly one URL line, found {len(urls)}")
    if len(signatures) != 1:
        raise ValueError(f"expected exactly one Guix Signature line, found {len(signatures)}")
    url_match, signature_match = urls[0], signatures[0]
    if url_match.start() <= signature_match.end():
        raise ValueError("URL line must follow the signed Signature line")

    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in base_url)
    ):
        raise ValueError("base URL must be an absolute HTTP(S) URL without query or fragment")

    original = url_match.group("value")
    parts = Path(original).parts
    if original.startswith("/") or ".." in parts:
        raise ValueError("narinfo URL must be a relative archive path")
    suffix = original if keep_path else original.rsplit("/", 1)[-1]
    target = f"{base_url.rstrip('/')}/{suffix}"
    return text[: url_match.start("value")] + target + text[url_match.end("value") :]


def convert_directory(
    source: Path,
    destination: Path,
    base_url: str,
    *,
    keep_path: bool = False,
) -> list[Path]:
    """Rewrite each signed *.narinfo in SOURCE into DESTINATION."""
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for narinfo in sorted(source.rglob("*.narinfo")):
        if narinfo.is_symlink() or not narinfo.is_file():
            raise ValueError(f"refusing non-regular narinfo entry: {narinfo}")
        before = narinfo.read_text(encoding="utf-8")
        before_signed = signed_prefix(before)
        after = rewrite_url(before, base_url, keep_path=keep_path)
        if signed_prefix(after) != before_signed:
            raise ValueError(f"refusing to change the signed payload of {narinfo.name}")
        target = destination / narinfo.name
        target.write_text(after, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="narinfo-to-release-urls",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--base-url", required=True,
                        help="absolute HTTP(S) base URL for release assets")
    parser.add_argument("--keep-path", action="store_true",
                        help="append the full narinfo URL path, not only its basename")
    args = parser.parse_args(argv)
    try:
        written = convert_directory(
            args.source, args.destination, args.base_url, keep_path=args.keep_path
        )
    except (OSError, ValueError) as exc:
        print(f"narinfo-to-release-urls: {exc}", file=sys.stderr)
        return 2
    print(f"narinfo-to-release-urls: rewrote {len(written)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
