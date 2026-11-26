# SPDX-License-Identifier: LicenseRef-Volnist
"""Keep the GCD 009 consensus and upstream implementation states distinct."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAMS = ROOT / "docs" / "UPSTREAMS.md"


class UpstreamStatusTests(unittest.TestCase):
    def test_gcd009_acceptance_is_not_reported_as_unknown(self) -> None:
        document = UPSTREAMS.read_text(encoding="utf-8")
        start = document.index("- [`GCD 009`]")
        end = document.find("\n- ", start + 1)
        section = document[start:] if end < 0 else document[start:end]

        self.assertIn("прийнятий консенсусний документ", section)
        self.assertIn("20.11.2026", section)
        self.assertIn("upstream implementation ще очікує", section)
        self.assertNotIn("результат на 26.11.2026 невідомий", section)
        self.assertNotIn("Якщо її приймуть", section)


if __name__ == "__main__":
    unittest.main()
