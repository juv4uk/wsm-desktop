# SPDX-License-Identifier: LicenseRef-Volnist
"""Every file of our own work carries the project licence, and only that one.

The project licence is ВОЛЬНІСТЬ (`LicenseRef-Volnist`), decided in #180. Files
that arrive with a different SPDX header are not a style problem: they assert a
different licence over the authors' own work, and a licence is not something a
merge should change by accident.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = "LicenseRef-Volnist"
HEADER = re.compile(r"SPDX-License-Identifier:?\s*=?\s*\"?([A-Za-z0-9.\-+]+)\"?")

# Third-party texts keep their own licence: we do not relicense other people's work.
SKIP_PREFIXES = ("LICENSES/", ".git/")


def files_with_headers() -> list[tuple[Path, list[str]]]:
    found: list[tuple[Path, list[str]]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any(relative.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if path.suffix in {".png", ".jpg", ".iso", ".zip", ".gz", ".xz", ".fd", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        identifiers = HEADER.findall(text)
        if identifiers:
            found.append((path, identifiers))
    return found


class LicenceHeaderTests(unittest.TestCase):
    def test_no_file_claims_a_licence_other_than_volnist(self) -> None:
        offenders: list[str] = []
        for path, identifiers in files_with_headers():
            for identifier in identifiers:
                if identifier != ALLOWED:
                    offenders.append(
                        f"{path.relative_to(ROOT)}: {identifier}"
                    )
        self.assertEqual(
            offenders,
            [],
            "files assert a licence other than the project licence: " + "; ".join(offenders),
        )

    def test_every_python_and_scheme_file_has_a_header(self) -> None:
        missing: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix not in {".py", ".scm"}:
                continue
            if path.relative_to(ROOT).as_posix().startswith("LICENSES/"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "SPDX-License-Identifier" not in text:
                missing.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(missing, [], f"no SPDX header: {missing}")

    def test_wsm_guix_packages_use_the_owner_license_object(self) -> None:
        module = (ROOT / "wsm" / "licenses.scm").read_text(encoding="utf-8")
        # Guix does not export the <license> constructor, so this module calls
        # it through `(@ (guix licenses) license)`.  The behavioral assertion is
        # tests/guix/compatibility-license-evaluation.scm, which evaluates
        # license-name and license-uri; here we only stop a silent substitution
        # of the owner's literal metadata with a different license.
        self.assertRegex(module, r"\((?:@ \(guix licenses\) )?license\b")
        for fragment in ('"ВОЛЬНІСТЬ"', '"file://LICENSE"', "LicenseRef-Volnist"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, module)
        self.assertTrue((ROOT / "LICENSE").is_file())

        for relative in (
            "wsm/packages/wsm.scm",
            "systems/live-iso.scm",
            "systems/live-compat.scm",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("(license wsm-license)", source)
                self.assertNotRegex(source, r"license[: ]+gpl3\+")
                self.assertIn("(wsm licenses)", source)

    def test_the_compatibility_lock_is_volnist_and_valid(self) -> None:
        """The Nonguix lock is our work even though it points at someone else's channel."""
        path = ROOT / "channels" / "compatibility.lock.scm"
        text = path.read_text(encoding="utf-8")
        self.assertIn(ALLOWED, text)
        self.assertNotIn("GPL-3.0", text)


if __name__ == "__main__":
    unittest.main()
