# SPDX-License-Identifier: LicenseRef-Volnist
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

# Documents a first-time visitor reads. The repository is written in Ukrainian
# first; English lives beside it as a translation with an .en.md suffix.
ENTRY_POINT_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)
TRANSLATION_SUFFIXES = (".uk.md", ".en.md")
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04ff]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
CYRILLIC_TOLERANCE = 1.0  # At least as many Cyrillic as Latin letters.
# Technical Ukrainian carries a lot of Latin: URLs, identifiers, schema field
# names, tool names. A canonical document is therefore judged by share, not by
# beating Latin outright. The lowest canonical document sits near 0.40; an
# English document sits near 0.01, so 0.25 separates them without guessing.
UKRAINIAN_RATIO_FLOOR = 0.25


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


def is_ukrainian(text: str) -> bool:
    """Return True when Cyrillic is the dominant script of the text."""
    latin = len(LATIN_PATTERN.findall(text))
    cyrillic = len(CYRILLIC_PATTERN.findall(text))
    return cyrillic > 0 and cyrillic >= latin * CYRILLIC_TOLERANCE


def canonical_of(path: Path) -> Path | None:
    """Return the canonical document for a translation file, or None."""
    name = path.name
    for suffix in TRANSLATION_SUFFIXES:
        if name.endswith(suffix):
            return path.with_name(name[: -len(suffix)] + ".md")
    return None


def is_ukrainian_dominant(text: str) -> bool:
    """True when Cyrillic makes up a meaningful share of the letters."""
    cyrillic = len(CYRILLIC_PATTERN.findall(text))
    latin = len(LATIN_PATTERN.findall(text))
    if cyrillic + latin == 0:
        return True  # nothing to judge: an empty or symbol-only document
    return cyrillic / (cyrillic + latin) >= UKRAINIAN_RATIO_FLOOR


def check_docs_language() -> list[str]:
    """Every document under docs/ is canonical in Ukrainian, or a *.en.md translation."""
    errors: list[str] = []
    for source in sorted((ROOT / "docs").rglob("*.md")):
        if source.name.endswith(".en.md"):
            continue
        if not is_ukrainian_dominant(source.read_text(encoding="utf-8")):
            errors.append(
                f"{source.relative_to(ROOT)}: documentation under docs/ is canonical in "
                f"Ukrainian; write the English text as a .en.md translation beside it"
            )
    return errors


def check_document_language() -> list[str]:
    """Entry points must be Ukrainian; translations must have an original."""
    errors: list[str] = []
    for relative in ENTRY_POINT_DOCUMENTS:
        source = ROOT / relative
        if not source.exists():
            errors.append(f"{relative}: entry-point document is missing")
            continue
        if not is_ukrainian(source.read_text(encoding="utf-8")):
            errors.append(
                f"{relative}: documentation is canonical in Ukrainian; put the English "
                f"text in a .en.md translation (see CONTRIBUTING.md, language policy)"
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
    errors = (
        check_links()
        + check_research_status()
        + check_document_language()
        + check_docs_language()
    )
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
