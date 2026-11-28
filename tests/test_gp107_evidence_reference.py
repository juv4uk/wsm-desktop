# SPDX-License-Identifier: LicenseRef-Volnist
"""WSM may cite GP107 benchmarks, but only with their provenance and bounds.

The canonical GPU harness and its raw artifacts live in
`juv4uk/gp107-nvidia-re`. WSM's performance document points at them instead of
copying them, and issue #511 sets what such a citation must carry: exact source
commit, GPU identity, driver/ICD, repeats, and the limits.

A number without those is not evidence, it is a memory of one. This test keeps
the citation complete, and keeps the two things that must never be claimed from
it — H170 board certification and a finished NVK comparison — from appearing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE = ROOT / "docs" / "PERFORMANCE.md"


class Gp107EvidenceReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PERFORMANCE.read_text(encoding="utf-8")
        start = cls.text.find("## GPU-докази GP107")
        assert start != -1, "the GP107 section is gone"
        rest = cls.text[start:]
        end = rest.find("\n## ", 1)
        cls.section = rest if end == -1 else rest[:end]

    def test_source_commit_is_named(self) -> None:
        self.assertRegex(self.section, r"gp107-nvidia-re@[0-9a-f]{7,40}")

    def test_gpu_identity_is_named(self) -> None:
        self.assertIn("10de:1c82", self.section)

    def test_driver_and_icd_are_named(self) -> None:
        self.assertIn("580.196.11", self.section)
        self.assertIn("nvidia_icd.json", self.section)

    def test_repeat_count_is_named(self) -> None:
        self.assertRegex(self.section, r"3\s+(успішн|повтор)")

    def test_it_does_not_claim_h170_certification(self) -> None:
        self.assertIn("не** сертифікація плати H170", self.section)

    def test_it_keeps_the_nvk_comparison_incomplete(self) -> None:
        self.assertIn("NOT_RUN", self.section)
        self.assertIn("незавершеним", self.section)

    def test_it_says_the_gbps_is_conditional_traffic(self) -> None:
        self.assertIn("умовний", self.section)

    def test_device_local_numbers_are_marked_not_accepted(self) -> None:
        self.assertIn("NOT ACCEPTED / EXPLORATORY", self.section)
        self.assertIn("не мав явних Vulkan", self.section)
        self.assertIn("memory dependencies", self.section)
        self.assertIn("CODE-UPDATED, PHYSICAL-RERUN-PENDING", self.section)
        self.assertIn("docs/22-device-local-transfer-and-compute-phases.md", self.section)
        self.assertIn("не** результат WSM", self.section)

    def test_it_points_at_the_canonical_issue(self) -> None:
        self.assertIn("gp107-nvidia-re/issues/18", self.section)


if __name__ == "__main__":
    unittest.main()
