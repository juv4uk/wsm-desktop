# SPDX-License-Identifier: LicenseRef-Volnist
"""The lock file decides what ships; each product needs an exact trusted set."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channels import (  # noqa: E402
    DEFAULT_LOCKS,
    ParseError,
    check,
    channels_of,
    main,
    parse,
    tokenize,
)

GOOD = '''
;; comments do not grant trust
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
  (branch #f)
  (commit "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
  (introduction
   (make-channel-introduction
    "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
    (openpgp-fingerprint
     "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5"))))
'''


class ParseTests(unittest.TestCase):
    def test_comments_are_dropped(self) -> None:
        tokens = tokenize("(a) ; (b)\n(c)")
        self.assertNotIn("b", tokens)

    def test_strings_keep_their_content_and_type(self) -> None:
        parsed = parse(tokenize('(url "https://example.org/x")'))
        self.assertEqual(parsed, ["url", "https://example.org/x"])
        self.assertEqual(type(parsed[1]).__name__, "SchemeString")

    def test_symbols_and_strings_are_not_interchangeable(self) -> None:
        parsed = parse(tokenize("(branch #f)"))
        self.assertEqual(type(parsed[1]).__name__, "SchemeSymbol")

    def test_quoted_symbol_loses_quote_in_channel_record(self) -> None:
        channels = channels_of(parse(tokenize(GOOD)))
        self.assertEqual(channels[0]["name"], "guix")
        self.assertEqual(channels[0]["branch"], "#f")

    def test_unbalanced_input_is_reported_not_raised(self) -> None:
        self.assertTrue(check("(list (channel"))

    def test_unterminated_string_is_rejected(self) -> None:
        with self.assertRaises(ParseError):
            tokenize('(url "https://example.org')

    def test_trailing_second_form_is_rejected(self) -> None:
        self.assertTrue(check(GOOD + "(list)"))


class PolicyTests(unittest.TestCase):
    def test_free_policy_accepts_its_exact_lock(self) -> None:
        self.assertEqual(check(GOOD, "free"), [])

    def test_free_policy_refuses_nonguix(self) -> None:
        problems = check(with_channel(NONGUIX), "free")
        self.assertTrue(any("unexpected channels" in problem for problem in problems))

    def test_compatibility_policy_requires_both_channels(self) -> None:
        problems = check(GOOD, "compatibility")
        self.assertTrue(any("missing required channels" in problem for problem in problems))

    def test_compatibility_accepts_exact_pinned_authenticated_nonguix(self) -> None:
        self.assertEqual(check(with_channel(NONGUIX), "compatibility"), [])

    def test_compatibility_rejects_a_different_repository_on_gitlab(self) -> None:
        fork = NONGUIX.replace(
            "https://gitlab.com/nonguix/nonguix",
            "https://gitlab.com/attacker/nonguix",
        )
        problems = check(with_channel(fork), "compatibility")
        self.assertTrue(any("unrecognized repository URL" in item for item in problems))

    def test_compatibility_rejects_guix_on_gitlab_even_if_host_is_allowed(self) -> None:
        guix_fork = GOOD.replace(
            "https://git.guix.gnu.org/guix.git",
            "https://gitlab.com/attacker/guix",
        )
        combined = guix_fork.rstrip()[:-1] + NONGUIX + ")"
        problems = check(combined, "compatibility")
        self.assertTrue(any("unrecognized repository URL" in item for item in problems))

    def test_compatibility_rejects_noncanonical_nonguix_introduction_commit(self) -> None:
        wrong = NONGUIX.replace(
            "897c1a470da759236cc11798f4e0a5f7d4d59fbc",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )
        problems = check(with_channel(wrong), "compatibility")
        self.assertTrue(any("canonical authenticated introduction commit" in item for item in problems))

    def test_compatibility_rejects_noncanonical_nonguix_fingerprint(self) -> None:
        wrong = NONGUIX.replace(
            "2A39 3FFF 68F4 EF7A 3D29 12AF 6F51 20A0 22FB B2D5",
            "AAAA BBBB CCCC DDDD EEEE FFFF 0000 1111 2222 3333",
        )
        problems = check(with_channel(wrong), "compatibility")
        self.assertTrue(any("canonical OpenPGP" in item for item in problems))

    def test_branch_must_be_literal_false(self) -> None:
        branch = NONGUIX.replace("(branch #f)", '(branch "main")')
        problems = check(with_channel(branch), "compatibility")
        self.assertTrue(any("branch must be the Scheme symbol #f" in item for item in problems))

    def test_duplicate_channel_names_are_refused(self) -> None:
        problems = check(with_channel(NONGUIX + NONGUIX), "compatibility")
        self.assertTrue(any("duplicate channel names" in item for item in problems))

    def test_duplicate_fields_are_refused(self) -> None:
        duplicate = NONGUIX.replace(
            "(name 'nonguix)",
            "(name 'nonguix) (name 'guix)",
        )
        problems = check(with_channel(duplicate), "compatibility")
        self.assertTrue(any("duplicate channel field" in item for item in problems))

    def test_unknown_fields_are_refused(self) -> None:
        extra = NONGUIX.replace(
            "(name 'nonguix)",
            '(name 'nonguix) (extra "ignored")',
        )
        problems = check(with_channel(extra), "compatibility")
        self.assertTrue(any("unknown channel field" in item for item in problems))

    def test_missing_branch_field_is_refused(self) -> None:
        missing = NONGUIX.replace("(branch #f)", "")
        problems = check(with_channel(missing), "compatibility")
        self.assertTrue(any("missing required fields" in item for item in problems))

    def test_compatibility_policy_refuses_an_unknown_channel(self) -> None:
        rogue = NONGUIX.replace("(name 'nonguix)", "(name 'random-thing)")
        problems = check(with_channel(rogue), "compatibility")
        self.assertTrue(any("unexpected channels" in item for item in problems))

    def test_unknown_policy_is_refused(self) -> None:
        self.assertTrue(check(GOOD, "whatever"))


class RepositoryTests(unittest.TestCase):
    def test_committed_free_lock_passes(self) -> None:
        self.assertEqual(main([]), 0)

    def test_compatibility_policy_uses_its_own_lock_path(self) -> None:
        self.assertEqual(
            DEFAULT_LOCKS["compatibility"],
            ROOT / "channels.compatibility.lock.scm",
        )
        # Until issue #210 supplies a real authenticated lock, the compatibility
        # check must fail closed rather than silently inspect the Free lock.
        if not DEFAULT_LOCKS["compatibility"].exists():
            self.assertEqual(main(["--policy", "compatibility"]), 2)
        else:
            self.assertEqual(main(["--policy", "compatibility"]), 0)

    def test_explicit_compatibility_lock_argument_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "channels.compatibility.lock.scm"
            lock.write_text(with_channel(NONGUIX), encoding="utf-8")
            self.assertEqual(
                main(["--policy", "compatibility", "--lock", str(lock)]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
