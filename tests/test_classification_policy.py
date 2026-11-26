# SPDX-License-Identifier: LicenseRef-Volnist
"""The three-level summary in code must be the one the policy defines.

`wsm_install.classification` collapses seven evidence states into three words.
That is legitimate only while the words are the same words the canonical policy
uses. The moment the code invents a fourth level or renames one, two truths
exist — and the doc gate cannot see it, because both files are valid markdown
and valid Python.

So this test reads the mapping table out of
`docs/HARDWARE-COMPATIBILITY-VERDICTS.md` §4.2 and compares it with the
constants the module actually uses.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install import classification  # noqa: E402

POLICY = ROOT / "docs" / "HARDWARE-COMPATIBILITY-VERDICTS.md"


def policy_tiers() -> set[str]:
    text = POLICY.read_text(encoding="utf-8")
    section = text.split("## 4.2", 1)[1].split("### Строк дії", 1)[0]
    return {
        match.group(1)
        for match in re.finditer(r"^\| `([a-z]+)` \|", section, re.MULTILINE)
    }


class ClassificationPolicyAgreementTests(unittest.TestCase):
    def test_module_levels_are_the_policy_tiers(self) -> None:
        self.assertEqual(
            {classification.CERTIFIED, classification.KNOWN, classification.UNKNOWN},
            policy_tiers(),
        )

    def test_module_levels_are_distinct(self) -> None:
        levels = [classification.CERTIFIED, classification.KNOWN, classification.UNKNOWN]
        self.assertEqual(len(levels), len(set(levels)))

    def test_every_subsystem_maps_to_a_declared_level(self) -> None:
        """A subsystem with no level would fall through to a silent default."""
        levels = {classification.CERTIFIED, classification.KNOWN, classification.UNKNOWN}
        empty_report: dict = {"devices": []}
        for subsystem in classification.SUBSYSTEMS:
            with self.subTest(subsystem=subsystem):
                verdict = classification.classify_subsystem(empty_report, subsystem)
                self.assertIn(verdict.level, levels)

    def test_missing_subsystem_keeps_coverage_unknown(self) -> None:
        """No record is not evidence of complete collection or device absence."""
        verdict = classification.classify_subsystem({"devices": []}, "storage")
        self.assertEqual(verdict.level, classification.UNKNOWN)
        self.assertEqual(verdict.coverage, "unknown")
        self.assertEqual(verdict.observation, "no-device-record")

    def test_candidate_only_is_known_under_the_canonical_policy(self) -> None:
        self.assertEqual(
            classification.EVIDENCE_TO_LEVEL["candidate-only"],
            classification.KNOWN,
        )

    def test_supported_test_needs_profile_bundle_before_certified_level(self) -> None:
        self.assertNotIn("supported-tested", classification.EVIDENCE_TO_LEVEL)


if __name__ == "__main__":
    unittest.main()
