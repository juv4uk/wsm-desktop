# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that every document has an owner and a way in.

Two failure modes this gate exists for, both observed in this repository:

1. **ADR without a registry row.** A decision document lands in
   ``docs/decisions/`` but ``docs/DECISIONS.md`` never learns about it, so two
   agents can hold two "canonical" decisions on the same topic.
2. **Document nobody can reach.** A protocol, policy or research note exists,
   is even referenced by a test, but no other document links to it. A reader
   starting from README cannot find it; the next agent writes it again.

The reachability rule is computed from the entry points, not from "any other
file links to me": two orphan documents linking each other are still orphans.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

# Documents a reader or an agent can start from without following a link.
ENTRY_POINTS = (
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)

REGISTRY = Path("docs/DECISIONS.md")
ADR_DIRECTORY = Path("docs/decisions")

LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
TRANSLATION_SUFFIXES = (".uk.md", ".en.md")

# README-файли всередині дерев коду документують каталог, а не проєкт.
# Вони не входять у граф докуів і не мусять бути досяжними з README.
CODE_DIRECTORIES = {"channels", "installer", "profiles", "systems", "schemas",
                    "tests", "scripts", "agents", "wsm", "wsm_hwcheck",
                    "wsm_install"}


def markdown_files(root: Path = ROOT) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if ".git" not in path.parts
        and "build" not in path.parts
        and path.relative_to(root).parts[0] not in CODE_DIRECTORIES
    )


def local_links(source: Path) -> list[Path]:
    """Return resolved local markdown targets linked from ``source``."""
    targets: list[Path] = []
    for match in LINK_PATTERN.finditer(source.read_text(encoding="utf-8")):
        raw = match.group(1).strip()
        if raw.startswith("<"):
            raw = raw[1:].split(">", 1)[0]
        else:
            raw = raw.split(None, 1)[0]
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        candidate = (source.parent / unquote(parsed.path)).resolve()
        if candidate.suffix == ".md" and candidate.exists():
            targets.append(candidate)
    return targets


def check_registry(root: Path = ROOT) -> list[str]:
    """Every ADR must be named in the registry."""
    errors: list[str] = []
    registry = root / REGISTRY
    if not registry.exists():
        return [f"{REGISTRY}: registry is missing"]
    registered = {target.resolve() for target in local_links(registry)}

    for adr in sorted((root / ADR_DIRECTORY).glob("*.md")):
        if adr.resolve() not in registered:
            errors.append(
                f"{adr.relative_to(root)}: ADR is not registered in {REGISTRY}; "
                f"add a topic row pointing at it"
            )
    return errors


def check_translations(root: Path = ROOT) -> list[str]:
    """A translation must be linked from its canonical document."""
    errors: list[str] = []
    for source in markdown_files(root):
        for suffix in TRANSLATION_SUFFIXES:
            if not source.name.endswith(suffix):
                continue
            canonical = source.with_name(source.name[: -len(suffix)] + ".md")
            if not canonical.exists():
                continue  # reported by check_docs.py
            if source.resolve() not in {link.resolve() for link in local_links(canonical)}:
                errors.append(
                    f"{source.relative_to(root)}: translation is not linked from "
                    f"{canonical.relative_to(root)}"
                )
    return errors


def reachable_documents(root: Path = ROOT) -> set[Path]:
    """Walk links from the entry points."""
    seen: set[Path] = set()
    queue: list[Path] = []
    for name in ENTRY_POINTS:
        path = (root / name).resolve()
        if path.exists():
            seen.add(path)
            queue.append(path)

    while queue:
        current = queue.pop()
        for target in local_links(current):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def check_reachability(root: Path = ROOT) -> list[str]:
    """Every document must be reachable from an entry point."""
    reachable = reachable_documents(root)
    return [
        f"{source.relative_to(root)}: document is not reachable from "
        f"{', '.join(ENTRY_POINTS)}; link it from the document that owns the topic"
        for source in markdown_files(root)
        if source.resolve() not in reachable
    ]


def check(root: Path = ROOT) -> list[str]:
    """All ownership rules in one list."""
    return check_registry(root) + check_translations(root) + check_reachability(root)


def main() -> int:
    errors = check()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Document ownership checks passed "
        f"({len(markdown_files())} documents, "
        f"{len(list((ROOT / ADR_DIRECTORY).glob('*.md')))} ADRs registered)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
