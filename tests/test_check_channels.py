# SPDX-License-Identifier: LicenseRef-Volnist
"""The lock file decides what ships. It must not be able to change quietly."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import check, channels_of, parse, tokenize  # noqa: E402

GOOD = '''
;; a comment that says "nonguix" must not matter
(list (channel
       (name 'guix)
       (url "https://git.guix.gnu.org/guix.git")
       (branch #f)
       (commit "4e5195be20d9b124df8a8bb69213412236e4668e")
       (introduction
        (make-channel-introduction
         "9edb3f66fd807b096b48283debdcddccfea34bad"
         (openpgp-fingerprint
          "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))))
'''


def with_channel(extra: str) -> str:
    return GOOD.rstrip()[:-1] + extra + ")"


NONGUIX = '''
 (channel
  (name 'nonguix)
  (url "https://gitlab.com/nonguix/nonguix")
  (commit "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
  (introduction (make-channel-introduction "x" (openpgp-fingerprint "y"))))'''


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

    def test_unbalanced_input_is_reported_not_raised(self) -> None:
        self.assertTrue(check("(list (channel"))


class RuleTests(unittest.TestCase):
    def test_the_real_shape_is_accepted(self) -> None:
        self.assertEqual(check(GOOD), [])

    def test_a_comment_mentioning_nonguix_does_not_fail_the_check(self) -> None:
        self.assertEqual(check(GOOD), [])

    def test_a_third_party_channel_is_refused(self) -> None:
        problems = check(with_channel(NONGUIX))
        self.assertTrue(any("nonguix" in problem for problem in problems))
        self.assertTrue(any("code execution" in problem for problem in problems))

    def test_plain_http_is_refused(self) -> None:
        text = GOOD.replace("https://git.guix.gnu.org", "http://git.guix.gnu.org")
        self.assertTrue(any("https" in problem for problem in check(text)))

    def test_unexpected_host_is_refused(self) -> None:
        text = GOOD.replace("https://git.guix.gnu.org/guix.git", "https://evil.example/guix.git")
        self.assertTrue(any("unexpected host" in problem for problem in check(text)))

    def test_branch_instead_of_commit_is_refused(self) -> None:
        text = GOOD.replace(
            '"4e5195be20d9b124df8a8bb69213412236e4668e"', '"master"'
        )
        self.assertTrue(any("full commit" in problem for problem in check(text)))

    def test_missing_introduction_is_refused(self) -> None:
        text = """
(list (channel
       (name 'guix)
       (url "https://git.guix.gnu.org/guix.git")
       (branch #f)
       (commit "4e5195be20d9b124df8a8bb69213412236e4668e")))
"""
        problems = check(text)
        self.assertTrue(any("authenticated" in problem for problem in problems), problems)

    def test_empty_list_is_refused(self) -> None:
        self.assertTrue(any("no channels" in problem for problem in check("(list)")))


class PolicyTests(unittest.TestCase):
    """The Compatibility image ships proprietary drivers; that is the product.

    What must not happen is an unnamed, unpinned or unauthenticated channel -
    not the existence of Nonguix itself.
    """

    def test_free_policy_refuses_nonguix(self) -> None:
        problems = check(with_channel(NONGUIX), "free")
        self.assertTrue(any("nonguix" in problem for problem in problems))

    def test_compatibility_policy_accepts_a_pinned_authenticated_nonguix(self) -> None:
        problems = check(with_channel(NONGUIX), "compatibility")
        self.assertEqual(problems, [])

    def test_compatibility_policy_still_requires_authentication(self) -> None:
        unauthenticated = NONGUIX.replace(
            '(introduction (make-channel-introduction "x" (openpgp-fingerprint "y")))', ""
        )
        problems = check(with_channel(unauthenticated), "compatibility")
        self.assertTrue(any("authenticated" in problem for problem in problems))

    def test_compatibility_policy_still_requires_a_full_commit(self) -> None:
        branch = NONGUIX.replace("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "main")
        problems = check(with_channel(branch), "compatibility")
        self.assertTrue(any("full commit" in problem for problem in problems))

    def test_compatibility_policy_refuses_an_unknown_host(self) -> None:
        text = with_channel(NONGUIX.replace("gitlab.com/nonguix/nonguix", "evil.example/x"))
        problems = check(text, "compatibility")
        self.assertTrue(any("unexpected host" in problem for problem in problems))

    def test_compatibility_policy_refuses_an_unnamed_channel(self) -> None:
        rogue = NONGUIX.replace("(name 'nonguix)", "(name 'random-thing)")
        problems = check(with_channel(rogue), "compatibility")
        self.assertTrue(any("random-thing" in problem for problem in problems))

    def test_unknown_policy_is_refused(self) -> None:
        self.assertTrue(check(GOOD, "whatever"))


class RepositoryTests(unittest.TestCase):
    def test_the_committed_lock_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_channels.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
