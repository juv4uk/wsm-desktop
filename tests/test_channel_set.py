# SPDX-License-Identifier: LicenseRef-Volnist
"""The WSM development set extends Guix's canonical channel defaults."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_SET = ROOT / "channels" / "wsm.scm"


class ChannelSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CHANNEL_SET.read_text(encoding="utf-8")

    def test_the_set_extends_guix_default_channels(self) -> None:
        self.assertIn("(use-modules (guix channels))", self.text)
        self.assertIn("%default-channels", self.text)
        self.assertIn("(cons*", self.text)
        self.assertNotIn("(name 'guix)", self.text)
        self.assertNotIn("make-channel-introduction", self.text)

    def test_the_wsm_channel_points_at_this_repository(self) -> None:
        self.assertIn("https://github.com/juv4uk/wsm-desktop.git", self.text)

    def test_the_wsm_channel_has_no_introduction_yet(self) -> None:
        """Claiming one would be a lie; the bootstrap needs the owner's key."""
        self.assertNotIn("make-channel-introduction", self.text)

    def test_the_file_says_it_is_not_authenticated(self) -> None:
        self.assertIn("не автентифікований", self.text)
        self.assertIn("--disable-authentication", self.text)

    def test_only_one_wsm_channel_is_added(self) -> None:
        self.assertEqual(self.text.count("(name 'wsm)"), 1)
        self.assertEqual(self.text.count("(channel"), 1)

    def test_wsm_channel_tracks_main(self) -> None:
        wsm_part = self.text[self.text.index("(name 'wsm)"): ]
        self.assertIn('(branch "main")', wsm_part)
        self.assertNotIn("(branch #f)", self.text)


if __name__ == "__main__":
    unittest.main()
