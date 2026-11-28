# SPDX-License-Identifier: LicenseRef-Volnist
"""The repository must be loadable as a Guix channel, and say honestly how far it is.

Issue #534 makes this repository the authoritative place for WSM's Guix
integration: a channel that exports our own package and system modules under the
`(wsm ...)` namespace. Three things can silently break that, and none of them
breaks a build today:

* a module outside the `(wsm ...)` namespace — it exists, but no channel user can
  reach it by the documented name;
* a Free module that pulls a nonfree dependency — the Free channel would start
  carrying Compatibility content without anyone deciding that;
* a claim of authentication before there is a signed introduction — the most
  expensive kind of wrong, because it is a claim about trust.

The channel file itself is upstream's for now: `channels/free.scm` returns
`%default-channels`. Turning it into a WSM channel needs an introduction signed
by the owner's key, which this repository may not generate or store.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSM = ROOT / "wsm"
CHANNELS = ROOT / "channels"

DEFINE_MODULE = re.compile(r"\(define-module\s+\(([^)]+)\)")
NONFREE = re.compile(r"nonguix|nongnu|linux\s+nvidia|nvidia-driver", re.IGNORECASE)


def modules_under(root: Path) -> dict[Path, str]:
    found: dict[Path, str] = {}
    for path in sorted(root.rglob("*.scm")):
        match = DEFINE_MODULE.search(path.read_text(encoding="utf-8"))
        if match:
            found[path] = match.group(1).split()
    return found


class ChannelContractTests(unittest.TestCase):
    def test_every_wsm_module_is_in_the_wsm_namespace(self) -> None:
        outside = {
            path.relative_to(ROOT).as_posix(): name
            for path, name in modules_under(WSM).items()
            if not name or name[0] != "wsm"
        }
        self.assertEqual(outside, {}, f"modules outside the (wsm ...) namespace: {outside}")

    def test_the_free_channel_does_not_carry_nonfree_modules(self) -> None:
        offenders = {
            path.relative_to(ROOT).as_posix(): NONFREE.pattern
            for path in sorted(WSM.rglob("*.scm"))
            if NONFREE.search(path.read_text(encoding="utf-8"))
        }
        self.assertEqual(
            offenders,
            {},
            "nonfree references in Free channel modules: " + ", ".join(offenders),
        )

    def test_the_channel_file_does_not_claim_authentication(self) -> None:
        """A channel without a signed introduction is not authenticated.

        `channels/free.scm` currently returns upstream `%default-channels`; that
        is honest. What must not appear is an `introduction` with a signing key
        that nobody verified on a real commit.
        """
        for path in sorted(CHANNELS.glob("*.scm")):
            text = path.read_text(encoding="utf-8")
            if "introduction" in text:
                self.assertIn(
                    "openpgp-fingerprint",
                    text,
                    f"{path.name}: an introduction must name the signing fingerprint",
                )

    def test_the_channel_documentation_states_the_trust_model(self) -> None:
        text = (CHANNELS / "README.md").read_text(encoding="utf-8")
        for phrase in ("introduction", "автентиф", "lock"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text.lower())

    def test_the_scan_finds_the_modules(self) -> None:
        """If the parser stops matching, the tests above would pass vacuously."""
        self.assertGreaterEqual(len(modules_under(WSM)), 2)


if __name__ == "__main__":
    unittest.main()
