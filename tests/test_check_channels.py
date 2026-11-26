# SPDX-License-Identifier: LicenseRef-Volnist
"""Структурні правила для окремих Free та Compatibility channel locks."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import (  # noqa: E402
    GUIX_INTRODUCTION_COMMIT,
    GUIX_INTRODUCTION_FINGERPRINT,
    NONGUIX_INTRODUCTION_COMMIT,
    NONGUIX_INTRODUCTION_FINGERPRINT,
    POLICY_LOCKS,
    SchemeString,
    check,
    channels_of,
    default_lock,
    main,
    parse,
    tokenize,
)

GUIX_COMMIT = "4e5195be20d9b124df8a8bb69213412236e4668e"
NONGUIX_COMMIT = "c" * 40


def channel(
    name: str,
    url: str,
    commit: str,
    introduction_commit: str,
    fingerprint: str,
) -> str:
    return f'''(channel
      (name '{name})
      (url "{url}")
      (branch #f)
      (commit "{commit}")
      (introduction
        (make-channel-introduction
          "{introduction_commit}"
          (openpgp-fingerprint "{fingerprint}"))))'''


GUIX_CHANNEL = channel(
    "guix",
    "https://git.guix.gnu.org/guix.git",
    GUIX_COMMIT,
    GUIX_INTRODUCTION_COMMIT,
    "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA",
)
NONGUIX_CHANNEL = channel(
    "nonguix",
    "https://gitlab.com/nonguix/nonguix",
    NONGUIX_COMMIT,
    NONGUIX_INTRODUCTION_COMMIT,
    NONGUIX_INTRODUCTION_FINGERPRINT,
)
GOOD_FREE = "(list " + GUIX_CHANNEL + ")"
GOOD_COMPATIBILITY = "(list " + GUIX_CHANNEL + " " + NONGUIX_CHANNEL + ")"


class ParseTests(unittest.TestCase):
    def test_comments_are_dropped(self) -> None:
        tokens = tokenize("(a) ; (b)\n(c)")
        self.assertNotIn("b", tokens)

    def test_strings_remain_distinct_from_symbols(self) -> None:
        value = parse(tokenize('(url "https://example.org/x")'))
        self.assertIsInstance(value[1], SchemeString)
        self.assertEqual(value[1], "https://example.org/x")

    def test_quoted_channel_name_remains_typed(self) -> None:
        record = channels_of(parse(tokenize(GOOD_FREE)))[0]
        self.assertEqual(record["name"], "guix")

    def test_unbalanced_parentheses_are_refused(self) -> None:
        self.assertTrue(check("(list (channel"))

    def test_unterminated_string_is_refused(self) -> None:
        self.assertTrue(check('(list (channel (url "https://example.org))'))


class FreePolicyTests(unittest.TestCase):
    def test_canonical_free_lock_is_accepted(self) -> None:
        self.assertEqual(check(GOOD_FREE, "free"), [])

    def test_official_savannah_mirror_is_accepted(self) -> None:
        mirror = GOOD_FREE.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.savannah.gnu.org/git/guix.git",
        )
        self.assertEqual(check(mirror, "free"), [])

    def test_nonguix_is_refused_by_free_policy(self) -> None:
        problems = check(GOOD_COMPATIBILITY, "free")
        self.assertTrue(any("exactly one entry" in item for item in problems))

    def test_duplicate_guix_channel_is_refused(self) -> None:
        problems = check("(list " + GUIX_CHANNEL + " " + GUIX_CHANNEL + ")", "free")
        self.assertTrue(any("exactly one entry" in item for item in problems))

    def test_unexpected_repository_path_on_allowed_host_is_refused(self) -> None:
        text = GOOD_FREE.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org/attacker.git",
        )
        self.assertTrue(any("exact allow-listed repository URL" in item for item in check(text, "free")))

    def test_noncanonical_guix_introduction_is_refused(self) -> None:
        text = GOOD_FREE.replace(GUIX_INTRODUCTION_COMMIT, "a" * 40)
        self.assertTrue(any("canonical GNU Guix trust root" in item for item in check(text, "free")))


class CompatibilityPolicyTests(unittest.TestCase):
    def test_two_distinct_pinned_channel_entries_are_structurally_accepted(self) -> None:
        self.assertEqual(check(GOOD_COMPATIBILITY, "compatibility"), [])

    def test_free_lock_is_not_a_compatibility_lock(self) -> None:
        problems = check(GOOD_FREE, "compatibility")
        self.assertTrue(any("exactly one entry" in item for item in problems))

    def test_unknown_channel_is_refused(self) -> None:
        rogue = channel(
            "random",
            "https://example.org/random",
            "d" * 40,
            "e" * 40,
            "F" * 40,
        )
        problems = check("(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility")
        self.assertTrue(any("exactly one entry" in item for item in problems))
        self.assertTrue(any("not permitted" in item for item in problems))

    def test_compatibility_channel_requires_exact_repository_url(self) -> None:
        bad = NONGUIX_CHANNEL.replace(
            "https://gitlab.com/nonguix/nonguix",
            "https://user@gitlab.com/nonguix/nonguix",
        )
        problems = check("(list " + GUIX_CHANNEL + " " + bad + ")", "compatibility")
        self.assertTrue(any("exact allow-listed repository URL" in item for item in problems))

    def test_compatibility_channel_rejects_nonguix_subpath_and_suffix_variants(self) -> None:
        variants = (
            "https://gitlab.com/nonguix/other",
            "https://gitlab.com/nonguix/nonguix.evil",
            "https://gitlab.com/nonguix/nonguix.git",
        )
        for url in variants:
            with self.subTest(url=url):
                rogue = NONGUIX_CHANNEL.replace(
                    "https://gitlab.com/nonguix/nonguix", url
                )
                problems = check(
                    "(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility"
                )
                self.assertTrue(
                    any("exact allow-listed repository URL" in item for item in problems)
                )

    def test_compatibility_channel_rejects_userinfo_port_query_and_fragment(self) -> None:
        variants = (
            "https://user@gitlab.com/nonguix/nonguix",
            "https://gitlab.com:443/nonguix/nonguix",
            "https://gitlab.com/nonguix/nonguix?ref=main",
            "https://gitlab.com/nonguix/nonguix#fragment",
        )
        for url in variants:
            with self.subTest(url=url):
                rogue = NONGUIX_CHANNEL.replace(
                    "https://gitlab.com/nonguix/nonguix", url
                )
                problems = check(
                    "(list " + GUIX_CHANNEL + " " + rogue + ")", "compatibility"
                )
                self.assertTrue(
                    any("exact allow-listed repository URL" in item for item in problems)
                )

    def test_compatibility_introduction_requires_full_fingerprint(self) -> None:
        bad = NONGUIX_CHANNEL.replace(NONGUIX_INTRODUCTION_FINGERPRINT, "not-a-fingerprint")
        problems = check("(list " + GUIX_CHANNEL + " " + bad + ")", "compatibility")
        self.assertTrue(any("full 40-hex-character fingerprint" in item for item in problems))

    def test_noncanonical_nonguix_introduction_commit_is_refused(self) -> None:
        bad = NONGUIX_CHANNEL.replace(NONGUIX_INTRODUCTION_COMMIT, "b" * 40)
        problems = check("(list " + GUIX_CHANNEL + " " + bad + ")", "compatibility")
        self.assertTrue(any("canonical Nonguix trust root" in item for item in problems))

    def test_noncanonical_nonguix_fingerprint_is_refused(self) -> None:
        bad = NONGUIX_CHANNEL.replace(NONGUIX_INTRODUCTION_FINGERPRINT, "A" * 40)
        problems = check("(list " + GUIX_CHANNEL + " " + bad + ")", "compatibility")
        self.assertTrue(any("canonical Nonguix trust root" in item for item in problems))


class AdversarialStructureTests(unittest.TestCase):
    def test_url_userinfo_port_query_and_fragment_are_refused(self) -> None:
        for url in (
            "https://user@git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org:443/guix.git",
            "https://git.guix.gnu.org/guix.git?branch=master",
            "https://git.guix.gnu.org/guix.git#fragment",
            "http://git.guix.gnu.org/guix.git",
            "https://evil.example/guix.git",
        ):
            with self.subTest(url=url):
                text = GOOD_FREE.replace("https://git.guix.gnu.org/guix.git", url)
                self.assertTrue(check(text, "free"))

    def test_branch_must_be_scheme_boolean_false(self) -> None:
        text = GOOD_FREE.replace("(branch #f)", '(branch "#f")')
        self.assertTrue(any("branch must be the Scheme boolean #f" in item for item in check(text, "free")))

    def test_url_must_be_a_scheme_string(self) -> None:
        text = GOOD_FREE.replace(
            '(url "https://git.guix.gnu.org/guix.git")',
            "(url https://git.guix.gnu.org/guix.git)",
        )
        self.assertTrue(any("must be a Scheme string" in item for item in check(text, "free")))

    def test_commit_must_be_a_scheme_string(self) -> None:
        text = GOOD_FREE.replace(
            f'(commit "{GUIX_COMMIT}")',
            f"(commit {GUIX_COMMIT})",
        )
        self.assertTrue(any("must be a Scheme string" in item for item in check(text, "free")))

    def test_branch_name_instead_of_full_commit_is_refused(self) -> None:
        text = GOOD_FREE.replace(GUIX_COMMIT, "main")
        self.assertTrue(any("full lowercase commit hash" in item for item in check(text, "free")))

    def test_duplicate_channel_field_is_refused(self) -> None:
        text = GOOD_FREE.replace("(name 'guix)", "(name 'guix) (name 'guix)")
        self.assertTrue(any("duplicate channel field" in item for item in check(text, "free")))

    def test_unknown_channel_field_is_refused(self) -> None:
        text = GOOD_FREE.replace("(name 'guix)", "(name 'guix) (mirror 'evil)")
        self.assertTrue(any("unexpected channel field" in item for item in check(text, "free")))

    def test_malformed_field_shape_is_refused(self) -> None:
        text = GOOD_FREE.replace("(branch #f)", "(branch #f #t)")
        self.assertTrue(any("exactly one value" in item for item in check(text, "free")))

    def test_introduction_comment_is_not_a_real_introduction(self) -> None:
        text = GOOD_FREE.replace(
            '(introduction\n        (make-channel-introduction\n          "9edb3f66fd807b096b48283debdcddccfea34bad"\n          (openpgp-fingerprint "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))',
            "",
        )
        self.assertTrue(check(text, "free"))

    def test_unknown_policy_is_refused(self) -> None:
        self.assertTrue(check(GOOD_FREE, "unknown"))


class LockSelectionTests(unittest.TestCase):
    def test_each_policy_has_its_own_default_lock(self) -> None:
        self.assertEqual(default_lock("free").name, "channels.lock.scm")
        self.assertEqual(default_lock("compatibility").name, "compatibility.lock.scm")
        self.assertNotEqual(POLICY_LOCKS["free"], POLICY_LOCKS["compatibility"])

    def test_compatibility_default_does_not_fall_back_to_free_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "compatibility.lock.scm"
            with patch.dict(POLICY_LOCKS, {"compatibility": missing}):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = main(["--policy", "compatibility"])
        self.assertEqual(result, 2)
        self.assertIn("compatibility.lock.scm", stderr.getvalue())

    def test_makefile_checks_compatibility_only_when_its_own_lock_exists(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("check-channels:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("--policy free --lock channels.lock.scm", target)
        self.assertIn("if test -f channels/compatibility.lock.scm", target)
        self.assertIn("--policy compatibility --lock channels/compatibility.lock.scm", target)
        self.assertIn("Compatibility lock NOT_CONFIGURED", target)


class RepositoryTests(unittest.TestCase):
    def test_committed_compatibility_lock_passes_structural_policy_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_channels.py"),
                "--policy",
                "compatibility",
                "--lock",
                str(ROOT / "channels" / "compatibility.lock.scm"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("structural", completed.stdout)
        self.assertIn("NOT verified", completed.stdout)

    def test_committed_free_lock_passes_structural_policy_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_channels.py"),
                "--policy",
                "free",
                "--lock",
                str(ROOT / "channels.lock.scm"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("structural", completed.stdout)
        self.assertIn("NOT verified", completed.stdout)


if __name__ == "__main__":
    unittest.main()
