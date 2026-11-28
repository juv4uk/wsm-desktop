# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC readers must be in the published pack, and the Python payload must not."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drivers" / "profiles" / "h170-free-packages.scm"
PACKAGES = ROOT / "wsm" / "packages" / "fpc-tools.scm"

FPC_TOOLS = (
    "wsm-hwcheck-fpc",
    "wsm-classify-fpc",
    "wsm-cpu-isa-fpc",
    "wsm-partition-fpc",
    "wsm-profile-fpc",
    "wsm-preflight-fpc",
    "wsm-install-fpc",
)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MANIFEST.read_text(encoding="utf-8")

    def test_every_fpc_reader_is_published(self) -> None:
        for name in FPC_TOOLS:
            self.assertIn(f'"{name}"', self.text, f"{name} is not in the pack")

    def test_every_published_reader_is_defined(self) -> None:
        """A manifest naming a package nobody defines fails only at build time."""
        definitions = PACKAGES.read_text(encoding="utf-8")
        for name in FPC_TOOLS:
            self.assertIn(f"(define-public {name}", definitions)

    def test_the_python_payload_is_still_excluded(self) -> None:
        self.assertNotIn('"wsm-tools"', self.text)

    def test_the_reason_for_the_exclusion_is_recorded(self) -> None:
        self.assertIn("#367", self.text)

    def test_the_language_ratification_is_recorded(self) -> None:
        self.assertIn("2026-11-28", self.text)


if __name__ == "__main__":
    unittest.main()
