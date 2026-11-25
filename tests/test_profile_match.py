# SPDX-License-Identifier: LicenseRef-Volnist
"""Matching a report to a profile: strict, and honest about what it cannot do."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.profile_match import match, report_pci_ids  # noqa: E402


def report(*pci_ids: str) -> dict:
    return {
        "devices": [
            {"device_id": f"dev-{index}", "identity": {"pci_id": pci}}
            for index, pci in enumerate(pci_ids)
        ]
    }


def bundle(slug: str, *pci_ids: str, mode: str = "all") -> dict:
    return {
        "profile": {"slug": slug},
        "hardware_signature": {"pci_ids": list(pci_ids), "match": mode},
    }


class ReportParsingTests(unittest.TestCase):
    def test_pci_ids_are_read_from_identity(self) -> None:
        self.assertEqual(report_pci_ids(report("10de:1c82", "8086:a170")), {"10de:1c82", "8086:a170"})

    def test_ids_are_lowercased(self) -> None:
        self.assertEqual(report_pci_ids(report("10DE:1C82")), {"10de:1c82"})

    def test_device_without_identity_contributes_nothing(self) -> None:
        self.assertEqual(report_pci_ids({"devices": [{"device_id": "x"}]}), set())


class MatchingTests(unittest.TestCase):
    def test_all_mode_requires_every_id(self) -> None:
        machine = report("10de:1c82", "8086:a170")
        matched, ambiguous, _ = match(machine, [bundle("test/fixture-board", "10de:1c82", "8086:a170")])
        self.assertEqual(matched, ["test/fixture-board"])
        self.assertEqual(ambiguous, [])

    def test_partial_match_is_not_a_match(self) -> None:
        machine = report("10de:1c82")
        matched, _, skipped = match(machine, [bundle("test/fixture-board", "10de:1c82", "8086:a170")])
        self.assertEqual(matched, [])
        self.assertTrue(any("does not match" in reason for reason in skipped))

    def test_any_mode_accepts_one_id(self) -> None:
        machine = report("10de:1c82")
        matched, _, _ = match(machine, [bundle("nvidia/pascal", "10de:1c82", mode="any")])
        self.assertEqual(matched, ["nvidia/pascal"])

    def test_bundle_without_signature_is_skipped_not_matched(self) -> None:
        machine = report("10de:1c82")
        matched, _, skipped = match(machine, [{"profile": {"slug": "manual/only"}}])
        self.assertEqual(matched, [])
        self.assertTrue(any("no hardware signature" in reason for reason in skipped))

    def test_two_matching_profiles_are_ambiguous_not_resolved(self) -> None:
        """Picking one would hide a real conflict between two verified claims."""
        machine = report("10de:1c82")
        matched, ambiguous, _ = match(
            machine,
            [
                bundle("a/first", "10de:1c82", mode="any"),
                bundle("b/second", "10de:1c82", mode="any"),
            ],
        )
        self.assertEqual(matched, [])
        self.assertEqual(sorted(ambiguous), ["a/first", "b/second"])

    def test_empty_report_matches_nothing(self) -> None:
        matched, _, _ = match({"devices": []}, [bundle("test/fixture-board", "10de:1c82")])
        self.assertEqual(matched, [])


if __name__ == "__main__":
    unittest.main()
