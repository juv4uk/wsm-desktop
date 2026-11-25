# SPDX-License-Identifier: LicenseRef-Volnist
"""Adversarial structural policy tests for separate Free and Compatibility locks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import (  # noqa: E402
    default_lock_for,
    check,
    channels_of,
    parse,
    tokenize,
)

GUIX_INTRODUCTION = """(introduction
  (make-channel-introduction
    "9edb3f66fd807b096b48283debdcddccfea34bad"
    (openpgp-fingerprint
      "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))"""
NONGUIX_INTRODUCTION = """(introduction
  (make-channel-introduction
    "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
    (openpgp-fingerprint
      "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5")))"""

GUIX_CHANNEL = """(channel
  (name 'guix)
  (url "https://git.guix.gnu.org/guix.git")
  (branch #f)
  (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
  """ + GUIX_INTRODUCTION + ")"
NONGUIX_CHANNEL = """(channel
  (name 'nonguix)
  (url "https://gitlab.com/nonguix/nonguix")
  (branch #f)
  (commit "6b8897cd6f3223b158c070cdc9cc638279f8c337")
  """ + NONGUIX_INTRODUCTION + ")"

GOOD_FREE = "(list " + GUIX_CHANNEL + ")"
GOOD_COMPATIBILITY = "(list " + GUIX_CHANNEL + " " + NONGUIX_CHANNEL + ")"


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"fixture fragment not found: {old!r}")
    return text.replace(old, new, 1)


class ParseTests(unittest.TestCase):
    def test_comments_are_dropped(self) -> None:
        tokens = tokenize("(a) ; (b)\n(c)")
        self.assertNotIn("b", tokens)

    def test_strings_keep_their_content(self) -> None:
        parsed = parse(tokenize('(url "https://example.org/x")'))
        self.assertEqual(parsed, ["url", "https://example.org/x"])

    def test_quoted_symbol_loses_the_quote(self) -> None:
        channels = channels_of(parse(tokenize(GOOD_FREE)))
        self.assertEqual(channels[0]["name"], "guix")

    def test_unbalanced_input_is_reported(self) -> None:
        self.assertTrue(check("(list (channel"))

    def test_unterminated_string_is_reported(self) -> None:
        self.assertTrue(check('(list (channel (url "https://example.org))'))


class PolicyTests(unittest.TestCase):
    def test_canonical_free_lock_is_accepted(self) -> None:
        self.assertEqual(check(GOOD_FREE, "free"), [])

    def test_official_savannah_mirror_is_allowed_for_guix(self) -> None:
        text = GOOD_FREE.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.savannah.gnu.org/git/guix.git",
        )
        self.assertEqual(check(text, "free"), [])

    def test_free_policy_refuses_nonguix(self) -> None:
        problems = check(GOOD_COMPATIBILITY, "free")
        self.assertTrue(any("free lock must declare channels" in item for item in problems))

    def test_compatibility_policy_requires_both_channels(self) -> None:
        problems = check(GOOD_FREE, "compatibility")
        self.assertTrue(any("compatibility lock must declare channels" in item for item in problems))

    def test_compatibility_policy_accepts_exact_guix_and_nonguix(self) -> None:
        self.assertEqual(check(GOOD_COMPATIBILITY, "compatibility"), [])

    def test_compatibility_policy_rejects_duplicate_nonguix(self) -> None:
        text = "(list " + GUIX_CHANNEL + " " + NONGUIX_CHANNEL + " " + NONGUIX_CHANNEL + ")"
        self.assertTrue(check(text, "compatibility"))

    def test_compatibility_policy_rejects_unknown_channel(self) -> None:
        rogue = NONGUIX_CHANNEL.replace("(name 'nonguix)", "(name 'random-thing)")
        text = "(list " + GUIX_CHANNEL + " " + rogue + ")"
        self.assertTrue(check(text, "compatibility"))

    def test_wrong_nonguix_repository_path_is_refused(self) -> None:
        text = GOOD_COMPATIBILITY.replace(
            "https://gitlab.com/nonguix/nonguix",
            "https://gitlab.com/attacker/nonguix",
        )
        self.assertTrue(check(text, "compatibility"))

    def test_url_userinfo_port_query_and_fragment_are_refused(self) -> None:
        urls = (
            "https://user@git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org:443/guix.git",
            "https://git.guix.gnu.org/guix.git?branch=master",
            "https://git.guix.gnu.org/guix.git#fragment",
        )
        for url in urls:
            with self.subTest(url=url):
                text = GOOD_FREE.replace("https://git.guix.gnu.org/guix.git", url)
                self.assertTrue(check(text, "free"))

    def test_branch_must_be_scheme_boolean_false(self) -> None:
        text = GOOD_FREE.replace("(branch #f)", '(branch "master")')
        self.assertTrue(check(text, "free"))

    def test_truncated_commit_is_refused(self) -> None:
        text = GOOD_FREE.replace(
            "4e5195be20d9b124df8a8bb69213412236e4668e",
            "master",
        )
        self.assertTrue(check(text, "free"))

    def test_wrong_guix_introduction_is_refused(self) -> None:
        text = GOOD_FREE.replace(GUIX_INTRODUCTION_COMMIT_PLACEHOLDER, "x") if False else replace_once(
            GOOD_FREE,
            "9edb3f66fd807b096b48283debdcddccfea34bad",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.assertTrue(any("canonical introduction" in item for item in check(text, "free")))

    def test_wrong_nonguix_fingerprint_is_refused(self) -> None:
        text = GOOD_COMPATIBILITY.replace(
            "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5",
            "0000 0000 0000 0000",
        )
        self.assertTrue(any("canonical introduction" in item for item in check(text, "compatibility")))

    def test_comment_only_introduction_is_refused(self) -> None:
        channel = GUIX_CHANNEL.replace(GUIX_INTRODUCTION, "")
        text = "(list " + channel + " ; " + GUIX_INTRODUCTION + "\n)"
        self.assertTrue(check(text, "free"))

    def test_duplicate_channel_field_is_refused(self) -> None:
        text = GOOD_FREE.replace("(name 'guix)", "(name 'guix) (name 'guix)")
        self.assertTrue(check(text, "free"))

    def test_non_symbol_channel_field_is_refused(self) -> None:
        text = GOOD_FREE.replace("(name 'guix)", "((nested) 'guix)")
        self.assertTrue(check(text, "free"))

    def test_unknown_policy_is_refused(self) -> None:
        self.assertTrue(check(GOOD_FREE, "unknown"))

    def test_default_lock_paths_are_separate(self) -> None:
        self.assertEqual(default_lock_for("free").name, "channels.lock.scm")
        self.assertEqual(default_lock_for("compatibility").name, "channels.compatibility.lock.scm")
        self.assertNotEqual(default_lock_for("free"), default_lock_for("compatibility"))


class RepositoryTests(unittest.TestCase):
    def test_free_lock_in_repository_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_channels.py"), "--policy", "free"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("structural policy", completed.stdout)
        self.assertIn("authentication remains a Guix", completed.stdout)

    def test_compatibility_lock_is_checked_when_it_exists(self) -> None:
        lock = ROOT / "channels.compatibility.lock.scm"
        if not lock.exists():
            self.skipTest("Compatibility lock is not committed yet; see issue #210")
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_channels.py"), "--policy", "compatibility"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
