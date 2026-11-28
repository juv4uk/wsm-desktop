# SPDX-License-Identifier: LicenseRef-Volnist
"""Refuse to publish Guix packages while the project's own blockers stand.

Publishing is the one action in this repository that leaves the machine: a
channel consumers pull from, or a binary cache they substitute from. Once it is
out, it cannot be recalled, and a licence mistake is not a bug you fix in the
next commit.

The repository already records two blockers that no amount of engineering can
close, because both are owner decisions:

* **#367** — `wsm-tools` declares `(license gpl3+)` while the repository is
  under `LicenseRef-Volnist`. The project's own rule is explicit: do not publish
  it as a release-ready channel package, and do not mask the problem by swapping
  the identifier.
* **#586** — no NVIDIA GP107 firmware may be included in or redistributed with
  the Free or Compatibility channel/ISO without written owner/legal clearance
  for the exact distribution model.

This checker reads the repository and reports what is still open. It is not a
substitute for the owner's decision; it exists so that decision cannot be
skipped by accident.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PACKAGE_FILE = Path("wsm") / "packages" / "wsm.scm"
REPO_LICENCE_MARKER = "LicenseRef-Volnist"

# Кожне визначення пакета в репозиторії, не лише канальне: ліцензійна
# суперечність #367 стосується трьох файлів, і публікація будь-якого з них
# розповсюджує код під хибними метаданими.
PACKAGE_DEFINITIONS = (
    Path("wsm") / "packages" / "wsm.scm",
    Path("systems") / "live-iso.scm",
    Path("systems") / "live-compat.scm",
)

# Системні визначення, які тягнуть nonfree: політика #586 забороняє
# розповсюджувати такі збірки без письмового clearance.
NONFREE_SYSTEMS = (
    Path("systems") / "live-compat.scm",
    Path("systems") / "compatibility.scm",
)
# Навмисно вузько: шукаємо самі nonfree-джерела, а не згадку моделі GPU.
# «GP107» у назві ядра — не firmware; перша версія правила давала через це
# шість хибних спрацювань на `(define wsm-linux-gp107`.
FIRMWARE_PATTERN = re.compile(
    r"nvidia-firmware|linux-firmware|nonguix|nongnu|firmware.*\.bin", re.IGNORECASE
)
PLACEHOLDER = re.compile(r"TODO|FIXME|0{32,}|\bplaceholder\b", re.IGNORECASE)


def declared_licence(text: str) -> str | None:
    """The Guix `license` field of the first package in the file."""
    match = re.search(r"\(license\s+([^)\s]+)\)", text)
    return match.group(1) if match else None


def problems(root: Path) -> list[str]:
    """Everything still blocking publication. Empty list means publishable."""
    found: list[str] = []
    package = root / PACKAGE_FILE

    if not package.is_file():
        found.append(f"{PACKAGE_FILE} is missing: nothing to publish")
        return found

    text = package.read_text(encoding="utf-8")

    licence = declared_licence(text)
    if licence is None:
        found.append(f"{PACKAGE_FILE} declares no license field (#367)")
    elif licence.startswith("gpl") or licence.startswith("("):
        found.append(
            f"{PACKAGE_FILE} declares ({licence}) while the repository is under "
            f"{REPO_LICENCE_MARKER} — #367 must be resolved by the owner; do not "
            "mask it by swapping the identifier"
        )

    if REPO_LICENCE_MARKER not in text:
        found.append(f"{PACKAGE_FILE} carries no {REPO_LICENCE_MARKER} SPDX header")

    if PLACEHOLDER.search(text):
        found.append(f"{PACKAGE_FILE} contains a placeholder or TODO in package metadata")

    if not (root / ".guix-authorizations").is_file():
        found.append(
            "channel has no .guix-authorizations: an unsigned channel may be built "
            "locally, but it must not be advertised as authenticated or pinned in a "
            "release lock (see docs/GUIX-CHANNEL.md)"
        )

    for definition in PACKAGE_DEFINITIONS:
        if definition == PACKAGE_FILE or not (root / definition).is_file():
            continue
        other_licence = declared_licence((root / definition).read_text(encoding="utf-8"))
        # Власний запис <license> теж правильний: він називає ту саму ліцензію,
        # що й заголовки файлів. Метадані мусять не суперечити, а не збігатися
        # рядком із маркером SPDX.
        if other_licence and other_licence not in (
            "license:volnist", "license-ref-volnist", REPO_LICENCE_MARKER
        ):
            found.append(
                f"{definition} declares ({other_licence}) while the repository is under "
                f"{REPO_LICENCE_MARKER} — the same #367 mismatch as {PACKAGE_FILE}"
            )

    for definition in NONFREE_SYSTEMS:
        path = root / definition
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split(";", 1)[0]
            if FIRMWARE_PATTERN.search(code) or "nongnu" in code:
                found.append(
                    f"{definition}:{number} pulls nonfree or firmware: "
                    f"{code.strip()[:70]} — #586 requires written clearance"
                )

    free_channel = root / "channels" / "free.scm"
    if free_channel.is_file():
        free_text = free_channel.read_text(encoding="utf-8")
        for number, line in enumerate(free_text.splitlines(), start=1):
            code = line.split(";", 1)[0]
            if FIRMWARE_PATTERN.search(code):
                found.append(
                    f"channels/free.scm:{number} references firmware or nonfree: "
                    f"{code.strip()[:80]} — #586 requires written clearance"
                )

    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report what still blocks publishing WSM Guix packages."
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="report blockers but exit 0 (for informational runs, never for publishing)",
    )
    arguments = parser.parse_args(argv)

    found = problems(Path(arguments.root))
    if not found:
        print("publication-readiness: no known blockers; the owner's go-ahead is still required")
        return 0

    print("\n".join(f"publication-readiness: {item}" for item in found), file=sys.stderr)
    print(
        "publication-readiness: NOT PUBLISHABLE — "
        f"{len(found)} blocker(s) above need an owner decision",
        file=sys.stderr,
    )
    return 0 if arguments.allow_blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
