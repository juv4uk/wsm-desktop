# SPDX-License-Identifier: LicenseRef-Volnist
"""The lock file decides what ships. Its structure must not change quietly."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import check, channels_of, parse, tokenize  # noqa: E402

INTRODUCTION = '''
(introduction
 (make-channel-introduction
  "9edb3f66fd807b096b48283debdcddccfea34bad"
  (openpgp-fingerprint
   "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))
'''

GOOD = '''
;; A comment mentioning nonguix does not add a channel.
(list (channel
       (name 'guix)
       (url "https://git.guix.gnu.org/guix.git")
       (branch #f)
       (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
       ''' + INTRODUCTION + '''))
'''

GOOD_SAVANNAH = GOOD.replace(
    "https://git.guix.gnu.org/guix.git",
    "https://git.savannah.gnu.org/git/guix.git",
)


def with_field(field: str, replacement: str) -> str:
    return GOOD.replace(field, replacement)


NONGUIX = '''
(channel
 (name 'nonguix)
 (url "https://gitlab.com/nonguix/nonguix")
 (branch #f)
 (commit "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
 ''' + INTRODUCTION + ''')
'''


class ParseTests(unittest.TestCase):
    def test_comments_are_dropped(self) -> None:
        tokens = tokenize("(a) ; (b)\n(c)")
        self.assertNotIn("b", tokens)

    def test_strings_keep_their_content(self) -> None:
        parsed = parse(tokenize('(url "https://example.org/x")'))
        self.assertEqual(parsed, ["url", "https://example.org/x"])

    def test_quoted_symbol_loses_the_quote(self) -> None:
        channels = channels_of(parse(tokenize(GOOD)))
        self.assertEqual(channels[0]["name"], "guix")

    def test_unbalanced_input_is_reported(self) -> None:
        self.assertTrue(check("(list (channel"))

    def test_unterminated_string_is_reported(self) -> None:
        self.assertTrue(check('(list (channel (url "https://example.org))'))


class RuleTests(unittest.TestCase):
    def test_canonical_guix_url_is_accepted(self) -> None:
        self.assertEqual(check(GOOD), [])

    def test_official_savannah_mirror_url_is_accepted(self) -> None:
        self.assertEqual(check(GOOD_SAVANNAH), [])

    def test_comment_mentioning_nonguix_does_not_add_a_channel(self) -> None:
        self.assertEqual(check(GOOD), [])

    def test_third_party_channel_is_refused(self) -> None:
        text = GOOD.rstrip()[:-1] + NONGUIX + ")"
        problems = check(text)
        self.assertTrue(any("exactly one channel" in item for item in problems))
        self.assertTrue(any("nonguix" in item for item in problems))

    def test_duplicate_guix_entry_is_refused(self) -> None:
        text = GOOD.rstrip()[:-1] + GOOD[GOOD.index("(channel"):GOOD.rindex(")")] + "))"
        self.assertTrue(any("exactly one channel" in item for item in check(text)))

    def test_unexpected_repository_path_on_allowed_host_is_refused(self) -> None:
        text = GOOD.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org/attacker.git",
        )
        self.assertTrue(any("exact allow-listed" in item for item in check(text)))

    def test_http_is_refused(self) -> None:
        text = GOOD.replace("https://git.guix.gnu.org", "http://git.guix.gnu.org")
        self.assertTrue(any("exact allow-listed" in item for item in check(text)))

    def test_url_userinfo_port_query_and_fragment_are_refused(self) -> None:
        urls = (
            "https://user@git.guix.gnu.org/guix.git",
            "https://git.guix.gnu.org:443/guix.git",
            "https://git.guix.gnu.org/guix.git?branch=master",
            "https://git.guix.gnu.org/guix.git#fragment",
        )
        for url in urls:
            with self.subTest(url=url):
                text = GOOD.replace(
                    "https://git.guix.gnu.org/guix.git",
                    url,
                )
                self.assertTrue(check(text))

    def test_branch_instead_of_false_is_refused(self) -> None:
        text = GOOD.replace("(branch #f)", '(branch "master")')
        self.assertTrue(any("branch #f" in item for item in check(text)))

    def test_full_commit_is_required(self) -> None:
        text = GOOD.replace(
            "4e5195be20d9b124df8a8bb69213412236e4668e",
            "master",
        )
        self.assertTrue(any("full lowercase commit" in item for item in check(text)))

    def test_duplicate_field_is_refused(self) -> None:
        text = GOOD.replace(
            '(name \\'guix)',
            '(name \\'guix) (name \\'guix)',
        )
        self.assertTrue(any("duplicate channel field" in item for item in check(text)))

    def test_missing_introduction_is_refused(self) -> None:
        text = GOOD.replace("       " + INTRODUCTION, "")
        self.assertTrue(any("missing required fields" in item for item in check(text)))

    def test_wrong_introduction_commit_is_refused(self) -> None:
        text = GOOD.replace(
            "9edb3f66fd807b096b48283debdcddccfea34bad",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.assertTrue(any("canonical Guix introduction" in item for item in check(text)))

    def test_wrong_or_malformed_fingerprint_is_refused(self) -> None:
        for fingerprint in (
            "0000 0000 0000 0000",
            "not-a-fingerprint",
        ):
            with self.subTest(fingerprint=fingerprint):
                text = GOOD.replace(
                    "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA",
                    fingerprint,
                )
                self.assertTrue(any("canonical Guix introduction" in item for item in check(text)))

    def test_introduction_only_in_comment_is_refused(self) -> None:
        text = GOOD.replace("       " + INTRODUCTION, "")
        text = text.replace("(name 'guix)", "(name 'guix)")
        self.assertTrue(any("missing required fields" in item for item in check(text)))

    def test_empty_list_is_refused(self) -> None:
        self.assertTrue(any("exactly one channel" in item for item in check("(list)")))


class RepositoryTests(unittest.TestCase):
    def test_committed_lock_passes_structural_policy(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_channels.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("cryptographic authentication remains", completed.stdout)


if __name__ == "__main__":
    unittest.main()
