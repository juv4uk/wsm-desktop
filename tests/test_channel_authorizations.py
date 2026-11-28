# SPDX-License-Identifier: LicenseRef-Volnist
"""Authorization parsing and historical keyring cross-checks must fail closed."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_channel_authorizations", ROOT / "scripts" / "check_channel_authorizations.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()

GOOD_FINGERPRINT = "1234 5678 9ABC DEF0 1234 5678 9ABC DEF0 1234 5678"
OTHER_FINGERPRINT = "ABCD EF01 2345 6789 ABCD EF01 2345 6789 ABCD EF01"
GOOD = f"""(authorizations
 (version 0)
 (("{GOOD_FINGERPRINT}"
   (name "WSM channel owner"))))
"""
GOOD_TWO = f"""(authorizations
 (version 0)
 (("{GOOD_FINGERPRINT}" (name "WSM channel owner"))
  ("{OTHER_FINGERPRINT}" (name "second owner"))))
"""
OTHER_ONLY = f"""(authorizations
 (version 0)
 (("{OTHER_FINGERPRINT}" (name "replacement owner"))))
"""


class ChannelAuthorizationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.keyring = self.root / "keyring"
        self.keyring.mkdir()
        self.git(["init", "--quiet"])
        self.git(["config", "user.name", "WSM test"])
        self.git(["config", "user.email", "wsm-test@example.invalid"])
        self.git(["commit", "--allow-empty", "-qm", "test repository baseline"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, arguments: list[str]):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )

    def write_authorizations(self, text: str) -> None:
        (self.root / ".guix-authorizations").write_text(text, encoding="utf-8")

    def commit_authorizations(self, text: str, message: str) -> None:
        self.write_authorizations(text)
        self.git(["add", ".guix-authorizations"])
        self.git(["commit", "-m", message])

    def write_key(self, name: str, fingerprint: str = GOOD_FINGERPRINT) -> Path:
        path = self.keyring / name
        path.write_text("synthetic public key fixture", encoding="utf-8")
        return path

    def gpg_success(self, fingerprint: str = GOOD_FINGERPRINT):
        compact = "".join(fingerprint.split())
        output = f"pub:::::::::\nfpr:::::::::{compact}:\n"
        return subprocess.CompletedProcess(["gpg"], 0, output, "")

    def patched_gpg(self, results: list[subprocess.CompletedProcess]):
        """Mock GPG while allowing the checker's real git-history commands."""
        real_run = subprocess.run
        result_iter = iter(results)

        def dispatch(command, *args, **kwargs):
            if command and command[0] == "git":
                return real_run(command, *args, **kwargs)
            if command and command[0] == "gpg":
                return next(result_iter)
            raise AssertionError(f"unexpected subprocess command: {command}")

        return patch.object(checker.subprocess, "run", side_effect=dispatch)

    def check_with_keyring(self, text: str, fingerprints: list[str]):
        self.write_authorizations(text)
        for index, fingerprint in enumerate(fingerprints):
            self.write_key(f"key-{index}.key", fingerprint)
        results = [self.gpg_success(fingerprint) for fingerprint in fingerprints]
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg(results),
        ):
            return checker.problems(self.root, keyring_dir=self.keyring)

    def test_absent_authorizations_are_not_bootstrapped(self) -> None:
        self.assertEqual(checker.problems(self.root), [])

    def test_absent_authorizations_fail_when_bootstrapped_is_required(self) -> None:
        found = checker.problems(self.root, require_bootstrapped=True)
        self.assertTrue(any("not bootstrapped" in item for item in found), found)

    def test_matching_authorization_and_keyring_pass(self) -> None:
        found = self.check_with_keyring(GOOD, [GOOD_FINGERPRINT])
        self.assertEqual(found, [])

    def test_guix_optional_metadata_does_not_require_a_name(self) -> None:
        text = (
            '(authorizations (version 0) '
            f'(("{GOOD_FINGERPRINT}" (owner "opaque-id") (note "optional metadata"))))'
        )
        self.assertEqual(checker.parse_authorizations(text), [GOOD_FINGERPRINT])

    def test_guix_allows_fingerprint_without_optional_metadata(self) -> None:
        text = f'(authorizations (version 0) (("{GOOD_FINGERPRINT}")))'
        self.assertEqual(checker.parse_authorizations(text), [GOOD_FINGERPRINT])

    def test_missing_keyring_argument_is_explicit_not_run(self) -> None:
        self.write_authorizations(GOOD)
        found = checker.problems(self.root)
        self.assertTrue(any("KEYRING_CHECK=NOT_RUN" in item for item in found), found)

    def test_empty_keyring_is_missing_every_authorized_key(self) -> None:
        self.write_authorizations(GOOD)
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("has no public .key export" in item for item in found), found)

    def test_one_of_two_authorized_keys_missing_is_refused(self) -> None:
        self.write_authorizations(GOOD_TWO)
        self.write_key("owner.key", GOOD_FINGERPRINT)
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([self.gpg_success(GOOD_FINGERPRINT)]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any(OTHER_FINGERPRINT in item and "no public .key" in item for item in found), found)

    def test_extra_key_never_authorized_in_history_is_refused(self) -> None:
        self.write_authorizations(GOOD)
        self.write_key("extra.key", OTHER_FINGERPRINT)
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([self.gpg_success(OTHER_FINGERPRINT)]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("unauthorized fingerprint" in item for item in found), found)

    def test_authorization_file_cannot_be_deleted_after_bootstrap(self) -> None:
        self.commit_authorizations(GOOD, "bootstrap test channel authorizations")
        self.git(["rm", ".guix-authorizations"])
        self.git(["commit", "-m", "remove test channel authorizations"])
        found = checker.problems(self.root)
        self.assertTrue(
            any("absent at HEAD but exists in channel history" in item for item in found),
            found,
        )

    def test_retired_authorization_remains_required_in_keyring(self) -> None:
        self.commit_authorizations(GOOD, "introduce first test authorization")
        self.commit_authorizations(OTHER_ONLY, "retire first test key")
        self.write_key("retired.key", GOOD_FINGERPRINT)
        self.write_key("current.key", OTHER_FINGERPRINT)
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([
                self.gpg_success(GOOD_FINGERPRINT),
                self.gpg_success(OTHER_FINGERPRINT),
            ]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertEqual(found, [])

    def test_missing_retired_key_is_refused_even_when_not_currently_authorized(self) -> None:
        self.commit_authorizations(GOOD, "introduce first test authorization")
        self.commit_authorizations(OTHER_ONLY, "retire first test key")
        self.write_key("current.key", OTHER_FINGERPRINT)
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([self.gpg_success(OTHER_FINGERPRINT)]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any(GOOD_FINGERPRINT in item and "no public .key export" in item for item in found), found)

    def test_duplicate_key_exports_are_refused(self) -> None:
        self.write_authorizations(GOOD)
        self.write_key("first.key", GOOD_FINGERPRINT)
        self.write_key("duplicate.key", GOOD_FINGERPRINT)
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([
                self.gpg_success(GOOD_FINGERPRINT),
                self.gpg_success(GOOD_FINGERPRINT),
            ]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("duplicate public-key exports" in item for item in found), found)

    def test_a_placeholder_is_refused(self) -> None:
        self.write_authorizations(GOOD.replace(GOOD_FINGERPRINT, "FULL OPENPGP FINGERPRINT WITH SPACES"))
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("placeholder" in item for item in found), found)

    def test_a_wrong_version_is_refused(self) -> None:
        self.write_authorizations(GOOD.replace("(version 0)", "(version 1)"))
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("version is 1" in item for item in found), found)

    def test_a_short_fingerprint_is_refused(self) -> None:
        self.write_authorizations(GOOD.replace(GOOD_FINGERPRINT, "1234 5678 9ABC DEF0"))
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("no full 40-hex OpenPGP fingerprint" in item for item in found), found)

    def test_fingerprint_only_in_a_comment_is_not_authorized(self) -> None:
        text = (
            "(authorizations (version 0) ())\n"
            f'; "{GOOD_FINGERPRINT}"\n'
        )
        self.write_authorizations(text)
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("non-empty list" in item for item in found), found)

    def test_fingerprint_in_an_unrelated_string_is_not_authorized(self) -> None:
        text = (
            '(authorizations (version 0) '
            f'(("not-a-fingerprint" (name "{GOOD_FINGERPRINT}"))))'
        )
        self.write_authorizations(text)
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("no full 40-hex OpenPGP fingerprint" in item for item in found), found)

    def test_malformed_nested_entry_is_refused(self) -> None:
        text = (
            '(authorizations (version 0) '
            f'(("{GOOD_FINGERPRINT}" "WSM channel owner")))'
        )
        self.write_authorizations(text)
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("malformed key/value metadata" in item for item in found), found)

    def test_empty_authorization_list_is_refused(self) -> None:
        self.write_authorizations("(authorizations (version 0) ())")
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("non-empty list" in item for item in found), found)

    def test_unbalanced_list_is_refused(self) -> None:
        self.write_authorizations("(authorizations (version 0) ((\"fingerprint\"")
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("unterminated list" in item for item in found), found)

    def test_duplicate_authorization_fingerprints_are_refused(self) -> None:
        text = (
            "(authorizations (version 0) ("
            f'("{GOOD_FINGERPRINT}" (name "one")) '
            f'("{GOOD_FINGERPRINT}" (name "two"))))'
        )
        self.write_authorizations(text)
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("duplicate authorized fingerprint" in item for item in found), found)

    def test_multiple_top_level_forms_are_refused(self) -> None:
        self.write_authorizations(GOOD + "(unrelated-form)\n")
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("exactly one top-level form" in item for item in found), found)

    def test_gpg_unavailable_is_keyring_not_run_and_fails_closed(self) -> None:
        self.write_authorizations(GOOD)
        self.write_key("owner.key")
        with patch.object(checker.shutil, "which", return_value=None):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("KEYRING_CHECK=NOT_RUN" in item and "gpg is unavailable" in item for item in found), found)

    def test_failed_gpg_show_keys_is_refused(self) -> None:
        self.write_authorizations(GOOD)
        self.write_key("owner.key")
        failure = subprocess.CompletedProcess(["gpg"], 2, "", "invalid key")
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([failure]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("cannot read public key" in item for item in found), found)

    def test_gpg_output_without_a_full_fingerprint_is_refused(self) -> None:
        self.write_authorizations(GOOD)
        self.write_key("owner.key")
        success_without_fpr = subprocess.CompletedProcess(["gpg"], 0, "pub:::::::::\n", "")
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            self.patched_gpg([success_without_fpr]),
        ):
            found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("exactly one primary public key" in item for item in found), found)

    def test_shallow_authorization_history_fails_closed(self) -> None:
        self.write_authorizations(GOOD)
        (self.root / ".git" / "shallow").write_text(
            self.git(["rev-parse", "HEAD"]).stdout.strip() + "\n",
            encoding="utf-8",
        )
        found = checker.problems(self.root, keyring_dir=self.keyring)
        self.assertTrue(any("shallow clone" in item for item in found), found)

    def test_the_repository_is_honest_about_its_state(self) -> None:
        found = checker.problems(ROOT)
        self.assertEqual(found, [])
        self.assertFalse((ROOT / ".guix-authorizations").is_file())


if __name__ == "__main__":
    unittest.main()
