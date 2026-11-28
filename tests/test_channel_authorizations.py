# SPDX-License-Identifier: LicenseRef-Volnist
"""Authorization parsing and public-key checks must fail closed."""

from __future__ import annotations

import contextlib
import io
import importlib.util
import subprocess
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
    spec.loader.exec_module(module)
    return module


checker = load_checker()

FINGERPRINT = "123456789ABCDEF0123456789ABCDEF012345678"
OTHER_FINGERPRINT = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
GOOD = """(authorizations
 (version 0)
 (("1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678"
   (name "WSM channel owner"))))
"""
PLACEHOLDER = GOOD.replace(
    "1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678",
    "FULL OPENPGP FINGERPRINT WITH SPACES",
)


class ChannelAuthorizationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, text: str) -> None:
        (self.root / ".guix-authorizations").write_text(text, encoding="utf-8")

    def write_key(self) -> Path:
        key = self.root / (FINGERPRINT + ".key")
        key.write_text("synthetic public key fixture", encoding="utf-8")
        return key

    def gpg_success(self, fingerprint: str = FINGERPRINT):
        output = f"pub:::::::::\nfpr:::::::::{fingerprint}:\n"
        return subprocess.CompletedProcess(["gpg"], 0, output, "")

    def test_absent_authorizations_are_not_bootstrapped(self) -> None:
        self.assertEqual(checker.problems(self.root), [])

    def test_absent_authorizations_fail_when_bootstrapped_is_required(self) -> None:
        found = checker.problems(self.root, require_bootstrapped=True)
        self.assertTrue(any("not bootstrapped" in item for item in found), found)

    def test_a_consistent_file_and_public_key_pass(self) -> None:
        self.write(GOOD)
        self.write_key()
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            patch.object(checker.subprocess, "run", return_value=self.gpg_success()),
        ):
            self.assertEqual(checker.problems(self.root), [])

    def test_a_placeholder_is_refused(self) -> None:
        self.write(PLACEHOLDER)
        found = checker.problems(self.root)
        self.assertTrue(any("placeholder" in item for item in found), found)

    def test_a_wrong_version_is_refused(self) -> None:
        self.write(GOOD.replace("(version 0)", "(version 1)"))
        found = checker.problems(self.root)
        self.assertTrue(any("version 0" in item for item in found), found)

    def test_a_short_fingerprint_is_refused(self) -> None:
        self.write(
            GOOD.replace(
                "1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678",
                "1234 5678 9ABC DEF0",
            )
        )
        found = checker.problems(self.root)
        self.assertTrue(any("invalid" in item or "no full" in item for item in found), found)

    def test_fingerprint_in_comment_is_not_authorized(self) -> None:
        self.write("""(authorizations (version 0) ())
; (("1234 5678 9ABC DEF0 1234  5678 9ABC DEF0 1234 5678"))
""")
        found = checker.problems(self.root)
        self.assertTrue(any("lists no full" in item for item in found), found)

    def test_fingerprint_in_unrelated_name_string_is_not_authorized(self) -> None:
        self.write(
            '(authorizations (version 0) (("not-a-fingerprint" '
            ' (name "1234 5678 9ABC DEF0 1234 5678 9ABC DEF0 1234 5678"))))'
        )
        found = checker.problems(self.root)
        self.assertTrue(any("invalid" in item or "no full" in item for item in found), found)

    def test_empty_authorization_list_is_refused(self) -> None:
        self.write("(authorizations (version 0) ())")
        found = checker.problems(self.root)
        self.assertTrue(any("lists no full" in item for item in found), found)

    def test_gpg_unavailable_fails_closed_when_key_file_exists(self) -> None:
        self.write(GOOD)
        self.write_key()
        with patch.object(checker.shutil, "which", return_value=None):
            found = checker.problems(self.root)
        self.assertTrue(any("gpg is unavailable" in item for item in found), found)

    def test_failed_gpg_show_keys_is_refused(self) -> None:
        self.write(GOOD)
        self.write_key()
        failure = subprocess.CompletedProcess(["gpg"], 2, "", "invalid key")
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            patch.object(checker.subprocess, "run", return_value=failure),
        ):
            found = checker.problems(self.root)
        self.assertTrue(any("gpg --show-keys failed" in item for item in found), found)

    def test_gpg_output_without_a_fingerprint_is_refused(self) -> None:
        self.write(GOOD)
        self.write_key()
        success_without_fpr = subprocess.CompletedProcess(["gpg"], 0, "pub:::::::::\n", "")
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            patch.object(checker.subprocess, "run", return_value=success_without_fpr),
        ):
            found = checker.problems(self.root)
        self.assertTrue(any("no valid full fingerprint" in item for item in found), found)

    def test_key_fingerprint_not_listed_in_authorizations_is_refused(self) -> None:
        self.write(GOOD)
        self.write_key()
        with (
            patch.object(checker.shutil, "which", return_value="/usr/bin/gpg"),
            patch.object(
                checker.subprocess,
                "run",
                return_value=self.gpg_success(OTHER_FINGERPRINT),
            ),
        ):
            found = checker.problems(self.root)
        self.assertTrue(any("not listed" in item for item in found), found)

    def test_no_key_files_is_explicitly_not_run_not_locally_consistent(self) -> None:
        self.write(GOOD)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = checker.main([str(self.root)])
        self.assertEqual(result, 0)
        self.assertIn("KEY_FILE_CHECK=NOT_RUN", output.getvalue())
        self.assertNotIn("locally consistent", output.getvalue())

    def test_the_repository_is_honest_about_its_state(self) -> None:
        """Today the repository has no authorizations; the check must say so."""
        found = checker.problems(ROOT)
        self.assertEqual(found, [])
        self.assertFalse((ROOT / ".guix-authorizations").is_file())


if __name__ == "__main__":
    unittest.main()
