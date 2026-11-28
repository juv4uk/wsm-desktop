# SPDX-License-Identifier: LicenseRef-Volnist
"""Contract for the unauthenticated diagnostic Guix channel-set smoke."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = ROOT / "channels" / "wsm.scm"
SMOKE = ROOT / "scripts" / "check-wsm-channel-set.sh"


class WSMChannelSetTests(unittest.TestCase):
    def test_unpinned_upstream_channel_has_an_explicit_branch(self) -> None:
        source = CHANNELS.read_text(encoding="utf-8")
        guix_start = source.index("(channel\n  (name 'guix)")
        wsm_start = source.index("(channel\n  (name 'wsm)")
        guix_form = source[guix_start:wsm_start]
        wsm_form = source[wsm_start:]
        self.assertIn('(branch "master")', guix_form)
        self.assertNotIn("(branch #f)", guix_form)
        self.assertIn('(branch "main")', wsm_form)

    def test_smoke_refusal_uses_default_authentication(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        default_call = source.split('AUTH_LOG="$WORK/authentication.log"', 1)[1].split(
            'DIAGNOSTIC_LOG="$WORK/diagnostic-only.log"', 1
        )[0]
        self.assertIn('time-machine -C "$CHANNELS" -- describe -f channels', default_call)
        self.assertNotIn("--disable-authentication", default_call)
        self.assertIn("default refusal did not identify the WSM channel", default_call)
        self.assertIn(
            "default refusal was not an authentication/introduction diagnostic",
            default_call,
        )

    def test_authentication_bypass_is_diagnostic_only(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        diagnostic = source.split('DIAGNOSTIC_LOG="$WORK/diagnostic-only.log"', 1)[1]
        self.assertIn("--disable-authentication", diagnostic)
        self.assertIn("WSM_CHANNELS_RESOLVED=guix,wsm", diagnostic)
        self.assertIn("WSM_CHANNEL_AUTHENTICATION=NOT_TESTED", diagnostic)


if __name__ == "__main__":
    unittest.main()
