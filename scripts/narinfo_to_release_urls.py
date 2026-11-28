# SPDX-License-Identifier: LicenseRef-Volnist
"""Point narinfo files at NAR archives hosted as release assets.

Why this exists: a static substitute cache needs two halves with very different
size profiles.

  * the metadata - `nix-cache-info', `*.narinfo', `signing-key.pub' - is a few
    kilobytes per store item and changes often;
  * the archives - `nar/*.nar.zst' - are tens to hundreds of megabytes and never
    change once published.

Putting both on GitHub Pages hits the 1 GiB site limit with a single desktop
closure. Putting both in git hits the 100 MiB per-file limit. So: archives go to
release assets, metadata goes to Pages, and the narinfo's `URL:' field is
rewritten to point at the asset.

The signature survives the rewrite because Guix signs a fingerprint of the store
path, the NAR hash, the NAR size and the references - the `URL:' is not part of
it. Rewriting it is therefore safe; rewriting `NarHash:' would not be.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

URL_LINE = re.compile(r"^URL:\s*(\S+)\s*$", re.M)
SIGNED_FIELDS = ("NarHash:", "NarSize:", "References:")


def rewrite_url(text: str, base_url: str, keep_path: bool = False) -> str:
    """Replace the `URL:' value with BASE_URL joined to the archive name."""
    match = URL_LINE.search(text)
    if match is None:
        raise ValueError("narinfo has no URL: field")
    original = match.group(1)
    name = original.rsplit("/", 1)[-1]
    target = f"{base_url.rstrip('/')}/{name}" if not keep_path else f"{base_url.rstrip('/')}/{original}"
    return URL_LINE.sub(f"URL: {target}", text, count=1)


def signed_fingerprint_fields(text: str) -> tuple[str, ...]:
    """The fields that must not change, for a caller that wants to assert it."""
    found = []
    for line in text.splitlines():
        for field in SIGNED_FIELDS:
            if line.startswith(field):
                found.append(line)
    return tuple(found)


def convert_directory(source: Path, destination: Path, base_url: str) -> list[Path]:
    """Rewrite every `*.narinfo' in SOURCE into DESTINATION."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for narinfo in sorted(source.rglob("*.narinfo")):
        before = narinfo.read_text(encoding="utf-8")
        after = rewrite_url(before, base_url)
        if signed_fingerprint_fields(before) != signed_fingerprint_fields(after):
            raise ValueError(f"refusing to rewrite signed fields of {narinfo.name}")
        target = destination / narinfo.name
        target.write_text(after, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="narinfo-to-release-urls", description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--base-url", required=True,
                        help="e.g. https://github.com/OWNER/REPO/releases/download/substitutes")
    parser.add_argument("--keep-path", action="store_true",
                        help="keep the nar/ prefix in the URL")
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
