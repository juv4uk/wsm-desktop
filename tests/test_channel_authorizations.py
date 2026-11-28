# SPDX-License-Identifier: LicenseRef-Volnist
"""Authorizations must be consistent before the owner signs an introduction.

`docs/GUIX-CHANNEL.md` puts the trust bootstrap in the owner's hands, and every
attempt costs a new signed commit. A leftover placeholder or a mistyped
fingerprint should therefore be caught before signing, not by
`guix git authenticate` afterwards.

The checker must also stay honest in the state we are actually in today: no
`.guix-authorizations` at all. That is "not bootstrapped", not "authenticated".
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_channel_authorizations", ROOT / "scripts" / "check_channel_authorizations.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()

GOOD = """(authorizations
 (version 0)
 (("1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678"
   (name "WSM channel owner"))))
"""

PLACEHOLDER = GOOD.replace("1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678",
                           "FULL OPENPGP FINGERPRINT WITH SPACES")


class ChannelAuthorizationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, text: str) -> None:
        (self.root / ".guix-authorizations").write_text(text, encoding="utf-8")

    def test_absent_authorizations_are_not_bootstrapped(self) -> None:
        self.assertEqual(checker.problems(self.root), [])

    def test_absent_authorizations_fail_when_bootstrapped_is_required(self) -> None:
        found = checker.problems(self.root, require_bootstrapped=True)
        self.assertTrue(any("not bootstrapped" in item for item in found), found)

    def test_a_consistent_file_passes(self) -> None:
        self.write(GOOD)
        self.assertEqual(checker.problems(self.root), [])

    def test_a_placeholder_is_refused(self) -> None:
        self.write(PLACEHOLDER)
        found = checker.problems(self.root)
        self.assertTrue(any("placeholder" in item for item in found), found)

    def test_a_wrong_version_is_refused(self) -> None:
        self.write(GOOD.replace("(version 0)", "(version 1)"))
        found = checker.problems(self.root)
        self.assertTrue(any("version 1" in item for item in found), found)

    def test_a_short_fingerprint_is_refused(self) -> None:
        self.write(GOOD.replace("1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678",
                                "1234 5678 9ABC DEF0"))
        found = checker.problems(self.root)
        self.assertTrue(any("no full OpenPGP fingerprint" in item for item in found), found)

    def test_the_repository_is_honest_about_its_state(self) -> None:
        """Today the repository has no authorizations; the check must say so."""
        found = checker.problems(ROOT)
        self.assertEqual(found, [])
        self.assertFalse((ROOT / ".guix-authorizations").is_file())


if __name__ == "__main__":
    unittest.main()
