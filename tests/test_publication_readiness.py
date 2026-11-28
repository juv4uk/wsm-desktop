# SPDX-License-Identifier: LicenseRef-Volnist
"""Publication must be refused while the owner's decisions are open.

Publishing leaves the machine and cannot be recalled. Two blockers in this
repository are owner decisions, not engineering tasks: the licence mismatch
(#367) and the absence of a signed channel introduction. The checker exists so
neither can be skipped by accident — and, just as important, so it does not
pretend they are closed.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_publication_readiness", ROOT / "scripts" / "check_publication_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()

PACKAGE_OK = """\
;; SPDX-License-Identifier: LicenseRef-Volnist
(define-public wsm-tools
  (package
    (name "wsm-tools")
    (version "0.1.0")
    (license license:volnist)))
"""

PACKAGE_MISMATCH = """\
;; SPDX-License-Identifier: LicenseRef-Volnist
(define-public wsm-tools
  (package
    (name "wsm-tools")
    (license gpl3+)))
"""


class PublicationReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "wsm" / "packages").mkdir(parents=True)
        (self.root / "channels").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_package(self, text: str) -> None:
        (self.root / "wsm" / "packages" / "wsm.scm").write_text(text, encoding="utf-8")

    def test_a_missing_package_is_reported(self) -> None:
        found = checker.problems(self.root)
        self.assertTrue(any("nothing to publish" in item for item in found), found)

    def test_the_licence_mismatch_is_reported(self) -> None:
        self.write_package(PACKAGE_MISMATCH)
        found = checker.problems(self.root)
        self.assertTrue(any("#367" in item for item in found), found)

    def test_an_unsigned_channel_is_reported(self) -> None:
        self.write_package(PACKAGE_OK)
        found = checker.problems(self.root)
        self.assertTrue(any("no .guix-authorizations" in item for item in found), found)

    def test_firmware_in_the_free_channel_is_reported(self) -> None:
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "channels" / "free.scm").write_text(
            "(use-modules (gnu packages nvidia-firmware))\n", encoding="utf-8"
        )
        found = checker.problems(self.root)
        self.assertTrue(any("#586" in item for item in found), found)

    def test_a_clean_tree_has_no_blockers(self) -> None:
        self.write_package(PACKAGE_OK)
        (self.root / ".guix-authorizations").write_text("(authorizations)\n", encoding="utf-8")
        (self.root / "channels" / "free.scm").write_text(
            "(use-modules (guix channels))\n%default-channels\n", encoding="utf-8"
        )
        self.assertEqual(checker.problems(self.root), [])

    def test_the_real_repository_is_currently_blocked(self) -> None:
        """If this ever passes, the owner resolved #367 — update the policy text."""
        found = checker.problems(ROOT)
        self.assertTrue(found, "the repository reports no blockers; #367 may be resolved")
        self.assertTrue(any("#367" in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
