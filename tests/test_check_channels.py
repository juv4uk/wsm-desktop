# SPDX-License-Identifier: LicenseRef-Volnist
"""Strict structural policy for separate Free and Compatibility Guix locks."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import (  # noqa: E402
    COMPATIBILITY_LOCK,
    FREE_LOCK,
    check,
    channels_of,
    main,
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
  (commit "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
  """ + NONGUIX_INTRODUCTION + ")"

FREE_LOCK_TEXT = "(list " + GUIX_CHANNEL + ")"
COMPATIBILITY_LOCK_TEXT = "(list " + GUIX_CHANNEL + " " + NONGUIX_CHANNEL + ")"


class ParseTests(unittest.TestCase):
    def test_comments_are_dropped(self) -> None:
        self.assertNotIn("nonguix", tokenize(";; nonguix\n(list)"))

    def test_strings_keep_their_content(self) -> None:
        parsed = parse(tokenize('(url "https://example.org/x")'))
        self.assertEqual(parsed, ["url", "https://example.org/x"])

    def test_quoted_symbol_loses_the_quote(self) -> None:
        channels = channels_of(parse(tokenize(FREE_LOCK_TEXT)))
        self.assertEqual(channels[0]["name"], "guix")

    def test_unbalanced_input_is_reported_not_raised(self) -> None:
        self.assertTrue(check("(list (channel"))

    def test_unterminated_string_is_reported(self) -> None:
        self.assertTrue(check('(list (channel (url "https://example.org))'))

    def test_trailing_second_form_is_rejected(self) -> None:
        self.assertTrue(check(FREE_LOCK_TEXT + " (list)"))


class FreePolicyTests(unittest.TestCase):
    def test_canonical_guix_repository_is_accepted(self) -> None:
        self.assertEqual(check(FREE_LOCK_TEXT, "free"), [])

    def test_official_savannah_mirror_is_accepted(self) -> None:
        mirror = FREE_LOCK_TEXT.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.savannah.gnu.org/git/guix.git",
        )
        self.assertEqual(check(mirror, "free"), [])

    def test_comment_mentioning_nonguix_does_not_add_a_channel(self) -> None:
        self.assertEqual(check(";; nonguix\n" + FREE_LOCK_TEXT, "free"), [])

    def test_free_policy_rejects_nonguix_channel(self) -> None:
        problems = check(COMPATIBILITY_LOCK_TEXT, "free")
        self.assertTrue(any("exactly 1 channel" in item for item in problems))
        self.assertTrue(any("nonguix" in item for item in problems))

    def test_free_policy_requires_one_channel(self) -> None:
        self.assertTrue(check("(list)", "free"))
        self.assertTrue(check(COMPATIBILITY_LOCK_TEXT, "free"))

    def test_free_policy_rejects_another_repository_on_an_allowed_host(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org/attacker.git",
        )
        self.assertTrue(any("exact allow-listed repository URL" in item for item in check(text, "free")))


class CompatibilityPolicyTests(unittest.TestCase):
    def test_exact_guix_and_nonguix_channels_are_accepted(self) -> None:
        self.assertEqual(check(COMPATIBILITY_LOCK_TEXT, "compatibility"), [])

    def test_compatibility_policy_requires_both_named_channels(self) -> None:
        self.assertTrue(any("exactly 2 channel" in item for item in check(FREE_LOCK_TEXT, "compatibility")))

    def test_compatibility_policy_rejects_duplicate_channel_names(self) -> None:
        duplicate = "(list " + GUIX_CHANNEL + " " + GUIX_CHANNEL + ")"
        problems = check(duplicate, "compatibility")
        self.assertTrue(any("duplicate channel names" in item for item in problems))

    def test_compatibility_policy_rejects_unnamed_third_party_channels(self) -> None:
        rogue = NONGUIX_CHANNEL.replace("(name 'nonguix)", "(name 'random-thing)")
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("exactly these channel names" in item for item in problems))

    def test_compatibility_policy_rejects_another_repo_on_gitlab_host(self) -> None:
        rogue = NONGUIX_CHANNEL.replace(
            "https://gitlab.com/nonguix/nonguix",
            "https://gitlab.com/attacker/other-project",
        )
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("exact allow-listed repository URL" in item for item in problems))

    def test_compatibility_policy_rejects_nonguix_subpath_and_suffix_variants(self) -> None:
        variants = (
            "https://gitlab.com/nonguix/other",
            "https://gitlab.com/nonguix/nonguix.evil",
            "https://gitlab.com/nonguix/nonguix.git",
        )
        for url in variants:
            with self.subTest(url=url):
                rogue = NONGUIX_CHANNEL.replace("https://gitlab.com/nonguix/nonguix", url)
                problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
                self.assertTrue(any("exact allow-listed repository URL" in item for item in problems))

    def test_compatibility_policy_rejects_userinfo_port_query_and_fragment(self) -> None:
        urls = (
            "https://user@gitlab.com/nonguix/nonguix",
            "https://gitlab.com:443/nonguix/nonguix",
            "https://gitlab.com/nonguix/nonguix?ref=main",
            "https://gitlab.com/nonguix/nonguix#fragment",
        )
        for url in urls:
            with self.subTest(url=url):
                rogue = NONGUIX_CHANNEL.replace("https://gitlab.com/nonguix/nonguix", url)
                problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
                self.assertTrue(any("exact allow-listed repository URL" in item for item in problems))

    def test_compatibility_policy_requires_nonguix_introduction(self) -> None:
        rogue = NONGUIX_CHANNEL.replace(NONGUIX_INTRODUCTION, "")
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("missing required fields" in item for item in problems))

    def test_compatibility_policy_rejects_wrong_nonguix_introduction(self) -> None:
        rogue = NONGUIX_CHANNEL.replace(
            "897c1a470da759236cc11798f4e0a5f7d4d59fbc",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("canonical introduction" in item for item in problems))

    def test_compatibility_policy_rejects_wrong_nonguix_fingerprint(self) -> None:
        rogue = NONGUIX_CHANNEL.replace(
            "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5",
            "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000",
        )
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("canonical introduction" in item for item in problems))

    def test_compatibility_policy_rejects_moving_branch(self) -> None:
        rogue = NONGUIX_CHANNEL.replace("(branch #f)", '(branch "main")')
        self.assertTrue(check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility"))

    def test_compatibility_policy_rejects_non_full_commit(self) -> None:
        rogue = NONGUIX_CHANNEL.replace(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "main",
        )
        self.assertTrue(check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility"))


class SchemeShapeTests(unittest.TestCase):
    def test_url_must_be_a_scheme_string_literal(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            '(url "https://git.guix.gnu.org/guix.git")',
            "(url https://git.guix.gnu.org/guix.git)",
        )
        self.assertTrue(any("must be a Scheme string" in item for item in check(text, "free")))

    def test_commit_must_be_a_scheme_string_literal(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            '(commit "4e5195be20d9b124df8a8bb69213412236e4668e")',
            "(commit 4e5195be20d9b124df8a8bb69213412236e4668e)",
        )
        self.assertTrue(any("must be a Scheme string" in item for item in check(text, "free")))

    def test_branch_string_false_is_not_boolean_false(self) -> None:
        text = FREE_LOCK_TEXT.replace("(branch #f)", '(branch "#f")')
        self.assertTrue(any("Scheme boolean #f" in item for item in check(text, "free")))

    def test_duplicate_channel_field_is_rejected(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            "(name 'guix)",
            "(name 'guix) (name 'guix)",
        )
        self.assertTrue(any("duplicate channel field" in item for item in check(text, "free")))

    def test_unknown_channel_field_is_rejected(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            "(name 'guix)",
            "(name 'guix) (extra 'value)",
        )
        self.assertTrue(any("unexpected channel field" in item for item in check(text, "free")))

    def test_missing_introduction_is_rejected_even_if_comment_mentions_it(self) -> None:
        comment = ";; " + GUIX_INTRODUCTION.replace("\\n", " ")
        text = FREE_LOCK_TEXT.replace(GUIX_INTRODUCTION, "") + "\\n" + comment + "\\n"
        self.assertTrue(any("missing required fields" in item for item in check(text, "free")))

    def test_wrong_guix_introduction_is_rejected(self) -> None:
        text = FREE_LOCK_TEXT.replace(
            "9edb3f66fd807b096b48283debdcddccfea34bad",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )
        self.assertTrue(any("canonical introduction" in item for item in check(text, "free")))

    def test_unknown_policy_is_rejected(self) -> None:
        self.assertTrue(check(FREE_LOCK_TEXT, "unknown"))


class CliTests(unittest.TestCase):
    def test_free_lock_default_is_canonical_repository_lock(self) -> None:
        self.assertEqual(FREE_LOCK.name, "channels.lock.scm")

    def test_compatibility_default_is_a_separate_lock_not_free_lock(self) -> None:
        self.assertEqual(COMPATIBILITY_LOCK.name, "channels.compatibility.lock.scm")
        self.assertNotEqual(FREE_LOCK, COMPATIBILITY_LOCK)

    def test_explicit_compatibility_lock_can_be_checked_without_ambient_channels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "channels.compatibility.lock.scm"
            lock.write_text(COMPATIBILITY_LOCK_TEXT, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--policy", "compatibility", "--lock", str(lock)])
        self.assertEqual(result, 0)
        self.assertIn("structural policy", stdout.getvalue())
        self.assertIn("cryptographic channel authentication", stdout.getvalue())

    def test_missing_compatibility_lock_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-compatibility.lock.scm"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main(["--policy", "compatibility", "--lock", str(missing)])
        self.assertEqual(result, 2)
        self.assertIn("cannot read", stderr.getvalue())


class RepositoryTests(unittest.TestCase):
    def test_committed_free_lock_passes_structural_policy(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_channels.py"),
                "--policy",
                "free",
                "--lock",
                str(FREE_LOCK),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("cryptographic channel authentication", completed.stdout)


if __name__ == "__main__":
    unittest.main()
