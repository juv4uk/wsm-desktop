# SPDX-License-Identifier: LicenseRef-Volnist
"""Authorizations must be consistent before the owner signs an introduction."""

from __future__ import annotations

import importlib.util
import sys
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
    # dataclasses resolves the class module through sys.modules at decoration time.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()

GOOD_FINGERPRINT = "1234 5678 9ABC DEF0 1234 5678 9ABC DEF0 1234 5678"
GOOD = f"""(authorizations
 (version 0)
 (("{GOOD_FINGERPRINT}"
   (name "WSM channel owner"))))
"""


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
        self.write(GOOD.replace(GOOD_FINGERPRINT, "FULL OPENPGP FINGERPRINT WITH SPACES"))
        found = checker.problems(self.root)
        self.assertTrue(any("placeholder" in item for item in found), found)

    def test_a_wrong_version_is_refused(self) -> None:
        self.write(GOOD.replace("(version 0)", "(version 1)"))
        found = checker.problems(self.root)
        self.assertTrue(any("version is 1" in item for item in found), found)

    def test_a_short_fingerprint_is_refused(self) -> None:
        self.write(GOOD.replace(GOOD_FINGERPRINT, "1234 5678 9ABC DEF0"))
        found = checker.problems(self.root)
        self.assertTrue(any("no full 40-hex OpenPGP fingerprint" in item for item in found), found)

    def test_a_fingerprint_in_a_comment_does_not_authorize_a_short_entry(self) -> None:
        comment = '; "AAAA BBBB CCCC DDDD EEEE FFFF 1111 2222 3333 4444"\n'
        self.write(GOOD.replace(GOOD_FINGERPRINT, "1234 5678 9ABC DEF0") + comment)
        found = checker.problems(self.root)
        self.assertTrue(any("no full 40-hex OpenPGP fingerprint" in item for item in found), found)

    def test_malformed_nested_entry_is_refused(self) -> None:
        malformed = GOOD.replace(
            f'("{GOOD_FINGERPRINT}"\n   (name "WSM channel owner"))',
            f'("{GOOD_FINGERPRINT}" "WSM channel owner")',
        )
        self.write(malformed)
        found = checker.problems(self.root)
        self.assertTrue(any("properties must be a list" in item for item in found), found)

    def test_multiple_top_level_forms_are_refused(self) -> None:
        self.write(GOOD + "(ignored-form)\n")
        found = checker.problems(self.root)
        self.assertTrue(any("exactly one top-level form" in item for item in found), found)

    def test_duplicate_fingerprints_are_refused(self) -> None:
        duplicate = GOOD.replace(
            f'("{GOOD_FINGERPRINT}"\n   (name "WSM channel owner"))',
            f'("{GOOD_FINGERPRINT}" (name "WSM channel owner")) '
            f'("{GOOD_FINGERPRINT}" (name "second owner"))',
        )
        self.write(duplicate)
        found = checker.problems(self.root)
        self.assertTrue(any("duplicate authorized fingerprint" in item for item in found), found)

    def test_missing_or_duplicate_name_is_refused(self) -> None:
        missing = GOOD.replace('(name "WSM channel owner")', '(comment "no display name")')
        self.write(missing)
        found = checker.problems(self.root)
        self.assertTrue(any("exactly one non-empty name" in item for item in found), found)

    def test_the_repository_is_honest_about_its_state(self) -> None:
        found = checker.problems(ROOT)
        self.assertEqual(found, [])
        self.assertFalse((ROOT / ".guix-authorizations").is_file())


if __name__ == "__main__":
    unittest.main()
