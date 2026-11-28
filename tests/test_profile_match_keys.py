# SPDX-License-Identifier: LicenseRef-Volnist
"""The matcher must read the keys the collector writes, not invented ones."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.profile_match import (  # noqa: E402
    match,
    pci_pairs_from_identity,
    report_pci_ids,
)


def bundle(slug: str, pci_ids: list[str], mode: str = "all") -> dict:
    return {
        "profile": {"slug": slug},
        "hardware_signature": {"pci_ids": pci_ids, "match": mode},
    }


class CollectorKeyTests(unittest.TestCase):
    """`wsm_hwcheck` writes vendor_id/device_id; nothing writes `pci_id`."""

    def test_the_collector_keys_produce_a_pair(self) -> None:
        pairs = pci_pairs_from_identity({"vendor_id": "0x10de", "device_id": "0x1c82"})
        self.assertEqual(pairs, {"10de:1c82"})

    def test_a_report_in_the_collector_shape_matches_a_profile(self) -> None:
        report = {
            "devices": [
                {"identity": {"vendor_id": "0x10de", "device_id": "0x1c82"}},
                {"identity": {"vendor_id": "0x8086", "device_id": "0x1912"}},
            ]
        }
        matched, ambiguous, skipped = match(report, [bundle("gigabyte/ga-h170-gaming3", ["10de:1c82"])])
        self.assertEqual(matched, ["gigabyte/ga-h170-gaming3"])
        self.assertEqual(ambiguous, [])
        self.assertEqual(skipped, [])

    def test_an_unknown_machine_matches_nothing_and_says_why(self) -> None:
        report = {"devices": [{"identity": {"vendor_id": "0x1234", "device_id": "0x5678"}}]}
        matched, _, skipped = match(report, [bundle("some/other", ["10de:1c82"])])
        self.assertEqual(matched, [])
        self.assertTrue(any("does not match" in reason for reason in skipped))

    def test_the_pre_joined_shape_still_works(self) -> None:
        """Older fixtures and hand-written reports keep working."""
        pairs = pci_pairs_from_identity({"pci_id": "10DE:1C82"})
        self.assertEqual(pairs, {"10de:1c82"})

    def test_report_pci_ids_reads_the_real_collector_output(self) -> None:
        report = {"devices": [{"identity": {"vendor_id": "0x10de", "device_id": "0x1c82"}}]}
        self.assertEqual(report_pci_ids(report), {"10de:1c82"})

    def test_the_drafter_uses_the_same_rule(self) -> None:
        """Two copies of this rule drifted once; there is now one."""
        source = (ROOT / "scripts" / "draft_profile_evidence.py").read_text(encoding="utf-8")
        self.assertIn("pci_pairs_from_identity", source)


if __name__ == "__main__":
    unittest.main()
