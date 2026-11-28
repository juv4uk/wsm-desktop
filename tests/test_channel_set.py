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

    def test_the_set_lists_both_channels(self) -> None:
        self.assertIn("(name 'guix)", self.text)
        self.assertIn("(name 'wsm)", self.text)

    def test_the_wsm_channel_points_at_this_repository(self) -> None:
        self.assertIn("https://github.com/juv4uk/wsm-desktop", self.text)

    def test_the_official_channel_keeps_its_introduction(self) -> None:
        """Dropping it would silently make the Guix channel unauthenticated too."""
        self.assertIn("make-channel-introduction", self.text)
        self.assertIn("9edb3f66fd807b096b48283debdcddccfea34bad", self.text)

    def test_the_wsm_channel_has_no_introduction_yet(self) -> None:
        """Claiming one would be a lie; the bootstrap needs the owner's key."""
        wsm_part = self.text[self.text.index("(name 'wsm)"):]
        self.assertNotIn("make-channel-introduction", wsm_part)

    def test_the_file_says_it_is_not_authenticated(self) -> None:
        self.assertIn("не автентифікований", self.text)
        self.assertIn("--disable-authentication", self.text)

    def test_it_is_a_single_list_form(self) -> None:
        """The structural checker expects exactly one form, like the lock files."""
        code = [
            line for line in self.text.splitlines()
            if line.strip() and not line.strip().startswith(";")
        ]
        self.assertTrue(code[0].startswith("(list"))
        depth = 0
        for char in "\n".join(code):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
        self.assertEqual(depth, 0)

    def test_floating_guix_channel_has_a_real_branch(self) -> None:
        """branch #f is valid only when paired with an exact commit pin."""
        guix_part = self.text[:self.text.index("(name 'wsm)")]
        self.assertIn('(branch "master")', guix_part)
        self.assertNotIn("(branch #f)", guix_part)

    def test_wsm_channel_tracks_main_without_claiming_an_introduction(self) -> None:
        wsm_part = self.text[self.text.index("(name 'wsm)"):]
        self.assertIn('(branch "main")', wsm_part)
        self.assertNotIn("make-channel-introduction", wsm_part)



if __name__ == "__main__":
    unittest.main()
