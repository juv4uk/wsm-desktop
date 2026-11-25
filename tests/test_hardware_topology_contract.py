# SPDX-License-Identifier: LicenseRef-Volnist
"""Structural guardrails for the proposed topology relationship contract."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "hardware" / "TOPOLOGY-RELATIONSHIPS.md"


class HardwareTopologyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CONTRACT.read_text(encoding="utf-8")
        cls.lower = cls.text.casefold()

    def test_topology_is_report_local_and_typed(self) -> None:
        for term in (
            "`node_id`",
            "`relationship_id`",
            "`from_node_id`",
            "`to_node_id`",
            "`kernel-exposed`",
            "`derived`",
            "`inferred`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, self.text)

    def test_usb_interfaces_are_separate_functions(self) -> None:
        self.assertIn("`interface-of`", self.text)
        self.assertIn("sibling", self.lower)
        self.assertIn("bInterface", self.text)

    def test_display_edges_do_not_claim_physical_cable_topology(self) -> None:
        self.assertIn("`exposed-by`", self.text)
        self.assertIn("`edid-observed-at`", self.text)
        self.assertIn("фізичний кабельний маршрут", self.lower)
        self.assertIn("не доводить", self.lower)

    def test_sysfs_collection_is_canonical_and_read_only(self) -> None:
        self.assertIn("/sys/devices", self.text)
        self.assertIn("read-only", self.lower)
        self.assertIn("не виконувати bind/unbind", self.lower)
        self.assertIn("testing abi", self.lower)

    def test_relationships_require_provenance_and_valid_references(self) -> None:
        self.assertIn("непорожній список provenance", self.lower)
        self.assertIn("dangling references", self.lower)
        self.assertIn("wrong direction", self.lower)
        self.assertIn("duplicate edges", self.lower)

    def test_privacy_and_unknown_relationships_are_preserved(self) -> None:
        for term in ("serial", "mac", "uuid", "wwn", "raw edid"):
            with self.subTest(term=term):
                self.assertIn(term, self.lower)
        self.assertIn("зв'язок не встановлено", self.lower)
        self.assertIn("не означає", self.lower)

    def test_v1_is_unchanged_and_new_topology_requires_major_revision(self) -> None:
        self.assertIn("additionalproperties: false", self.lower)
        self.assertIn("v1.0.0 незмінною", self.lower)
        self.assertIn("major schema revision", self.lower)
        self.assertIn("lossy adapter", self.lower)


if __name__ == "__main__":
    unittest.main()
