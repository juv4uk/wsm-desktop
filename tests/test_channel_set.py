# SPDX-License-Identifier: LicenseRef-Volnist
"""The channel set that makes (wsm packages wsm) reachable without -L."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_SET = ROOT / "channels" / "wsm.scm"


class ChannelSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CHANNEL_SET.read_text(encoding="utf-8")

    def test_the_set_extends_the_canonical_guix_defaults(self) -> None:
        """Do not fork/copy the official channel record into this channel set."""
        self.assertIn("(use-modules (guix channels))", self.text)
        self.assertIn("%default-channels", self.text)
        self.assertIn("(cons*", self.text)
        self.assertNotIn("(name 'guix)", self.text)
        self.assertIn("(name 'wsm)", self.text)

    def test_the_wsm_channel_points_at_this_repository(self) -> None:
        self.assertIn("https://github.com/juv4uk/wsm-desktop", self.text)

    def test_the_wsm_channel_has_no_introduction_yet(self) -> None:
        """Claiming one would be a lie; the bootstrap needs the owner's key."""
        wsm_part = self.text[self.text.index("(name 'wsm)"):]
        self.assertNotIn("make-channel-introduction", wsm_part)

    def test_the_file_says_it_is_not_authenticated(self) -> None:
        self.assertIn("unauthenticated", self.text.lower())
        self.assertIn("--disable-authentication", self.text)

    def test_channel_expression_is_balanced(self) -> None:
        """The import and channel-set expression must both be complete."""
        code = "\n".join(
            line for line in self.text.splitlines()
            if line.strip() and not line.strip().startswith(";")
        )
        depth = 0
        for char in code:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                self.assertGreaterEqual(depth, 0)
        self.assertEqual(depth, 0)
        self.assertTrue(code.startswith("(use-modules (guix channels))"))


if __name__ == "__main__":
    unittest.main()
