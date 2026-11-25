# SPDX-License-Identifier: GPL-3.0-or-later
"""Check local Markdown links and research-document status headers."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
STATUS_PATTERN = re.compile(r"(?m)^-?\s*(?:Статус|Status):")
STATUS_HEADER_LINES = 20


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "build" not in path.parts
    )


def local_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith("<"):
        target = target[1:].split(">", 1)[0]
    else:
        target = target.split(None, 1)[0]

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    decoded = unquote(parsed.path)
    return (source.parent / decoded).resolve()


def check_links() -> list[str]:
    errors: list[str] = []
    for source in markdown_files():
        text = source.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            candidate = local_target(source, match.group(1))
            if candidate is None:
                continue
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"{source.relative_to(ROOT)}: link leaves repository: "
                    f"{match.group(1)!r}"
                )
                continue
            if not candidate.exists():
                errors.append(
                    f"{source.relative_to(ROOT)}: missing local link target "
                    f"{match.group(1)!r}"
                )
    return errors


def check_research_status() -> list[str]:
    """Every document under docs/hardware/ must state its status near the top.

    The directory mixes implemented contracts with open research. Without a
    status header a reader cannot tell which is which, and a research note is
    easily mistaken for a commitment.
    """
    errors: list[str] = []
    for source in sorted((ROOT / "docs" / "hardware").glob("*.md")):
        head = "\n".join(source.read_text(encoding="utf-8").splitlines()[:STATUS_HEADER_LINES])
        if not STATUS_PATTERN.search(head):
            errors.append(
                f"{source.relative_to(ROOT)}: missing a 'Статус:' or 'Status:' "
                f"line in the first {STATUS_HEADER_LINES} lines"
            )
    return errors


def main() -> int:
    errors = check_links() + check_research_status()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Documentation checks passed "
        f"({len(markdown_files())} files, "
        f"{len(list((ROOT / 'docs' / 'hardware').glob('*.md')))} hardware documents)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
