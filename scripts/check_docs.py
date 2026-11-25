# SPDX-License-Identifier: GPL-3.0-or-later
"""Check local Markdown links, status headers and documentation languages."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
STATUS_PATTERN = re.compile(r"(?m)^-?\s*(?:Статус|Status):")
STATUS_HEADER_LINES = 20

# Documents a first-time visitor reads. They are canonical in English; every
# other tracked document under docs/ is canonical in Ukrainian.
ENTRY_POINT_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)
TRANSLATION_SUFFIXES = (".uk.md", ".en.md")
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04ff]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
CYRILLIC_TOLERANCE = 0.02


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


def is_english(text: str) -> bool:
    """Return True when the text is Latin-script with no meaningful Cyrillic."""
    latin = len(LATIN_PATTERN.findall(text))
    cyrillic = len(CYRILLIC_PATTERN.findall(text))
    return latin > 0 and cyrillic <= latin * CYRILLIC_TOLERANCE


def canonical_of(path: Path) -> Path | None:
    """Return the canonical document for a translation file, or None."""
    name = path.name
    for suffix in TRANSLATION_SUFFIXES:
        if name.endswith(suffix):
            return path.with_name(name[: -len(suffix)] + ".md")
    return None


def check_document_language() -> list[str]:
    """Entry points must be English; translations must have an original."""
    errors: list[str] = []
    for relative in ENTRY_POINT_DOCUMENTS:
        source = ROOT / relative
        if not source.exists():
            errors.append(f"{relative}: entry-point document is missing")
            continue
        if not is_english(source.read_text(encoding="utf-8")):
            errors.append(
                f"{relative}: entry-point documents are canonical in English "
                f"(see CONTRIBUTING.md, documentation language policy)"
            )

    for source in markdown_files():
        canonical = canonical_of(source)
        if canonical is not None and not canonical.exists():
            errors.append(
                f"{source.relative_to(ROOT)}: translation without a canonical "
                f"original at {canonical.relative_to(ROOT)}"
            )
    return errors


def main() -> int:
    errors = check_links() + check_research_status() + check_document_language()
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
