# SPDX-License-Identifier: LicenseRef-Volnist
"""The Omarchy regression register must not claim coverage it does not have.

The register in `docs/LESSONS-FROM-OMARCHY.md` maps each upstream failure class
to a WSM prevent rule, a detect rule, a status and an evidence reference. A
table like that rots in one direction only: a test gets renamed or deleted, the
row keeps saying `covered`, and the next reader trusts it.

So the evidence is checked, not just read:

* status must come from the closed vocabulary;
* `covered` and `partial` rows must cite `tests/<file>::<method>` that exists;
* `not-covered` and `out-of-scope` rows must not cite anything, because a
  reference there would be a claim of coverage by another name.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "LESSONS-FROM-OMARCHY.md"

STATUSES = {"covered", "partial", "not-covered", "out-of-scope"}
EVIDENCE_STATUSES = {"covered", "partial"}
ROW = re.compile(r"^\|\s*(?P<row>.+?)\s*\|\s*$")
EVIDENCE = re.compile(r"`(?P<path>tests/[\w./-]+\.py)::(?P<method>test_\w+)`")
MINIMUM_ROWS = 14


def register_rows(text: str) -> list[list[str]]:
    """Return the cells of the register table, without the header and rule rows."""
    rows: list[list[str]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("| Клас |"):
            inside = True
            continue
        if inside:
            if not line.startswith("|"):
                break
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            match = ROW.match(line)
            if match:
                rows.append([cell.strip() for cell in match.group("row").split(" | ")])
    return rows


class OmarchyRegisterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = REGISTER.read_text(encoding="utf-8")
        self.rows = register_rows(self.text)

    def test_register_exists_and_is_not_empty(self) -> None:
        self.assertGreaterEqual(
            len(self.rows),
            MINIMUM_ROWS,
            f"register has {len(self.rows)} rows; it must not shrink silently",
        )

    def test_every_row_has_five_cells(self) -> None:
        for row in self.rows:
            self.assertEqual(len(row), 5, row)

    def test_status_comes_from_the_closed_vocabulary(self) -> None:
        for row in self.rows:
            status = row[3].strip("`")
            self.assertIn(status, STATUSES, f"{row[0]}: unexpected status {status!r}")

    def test_covered_rows_cite_an_existing_test(self) -> None:
        for row in self.rows:
            status = row[3].strip("`")
            if status not in EVIDENCE_STATUSES:
                continue
            matches = list(EVIDENCE.finditer(row[4]))
            self.assertTrue(matches, f"{row[0]}: {status} row cites no test")
            for match in matches:
                path = ROOT / match.group("path")
                self.assertTrue(path.exists(), f"{row[0]}: missing file {path}")
                source = path.read_text(encoding="utf-8")
                self.assertIn(
                    f"def {match.group('method')}(",
                    source,
                    f"{row[0]}: {match.group('path')} has no {match.group('method')}",
                )

    def test_untrusted_theme_execution_is_not_claimed_covered_by_channel_policy(self) -> None:
        rows = [
            row for row in self.rows
            if "CVE-2026-108913" in row[0]
        ]
        self.assertEqual(len(rows), 1, "Omarchy theme/plugin execution must have one explicit row")
        self.assertEqual(rows[0][3].strip("`"), "out-of-scope")
        self.assertEqual(rows[0][4], "—")

    def test_nonfree_channel_policy_has_its_own_evidence_row(self) -> None:
        rows = [
            row for row in self.rows
            if "Free payload" in row[0]
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3].strip("`"), "covered")
        self.assertIn(
            "tests/test_check_channels.py::test_nonguix_is_refused_by_free_policy",
            rows[0][4],
        )

    def _row_for_source(self, source: str) -> list[str]:
        matches = [row for row in self.rows if source in row[0]]
        self.assertEqual(len(matches), 1, f"expected one row for {source!r}")
        return matches[0]

    def test_usb_metadata_injection_is_not_mapped_to_disk_refusal(self) -> None:
        row = self._row_for_source("Omarchy #8129")
        self.assertIn("Hyprland Lua", row[0])
        self.assertEqual(row[3].strip("`"), "out-of-scope")
        self.assertEqual(row[4], "—")

    def test_unresolved_fido2_migration_is_not_mapped_to_journal(self) -> None:
        row = self._row_for_source("Omarchy #16421")
        self.assertIn("FIDO2 migration", row[0])
        self.assertEqual(row[3].strip("`"), "out-of-scope")
        self.assertEqual(row[4], "—")

    def test_legacy_bios_layout_does_not_claim_multidisk_boot_order(self) -> None:
        """Boot order belongs to the firmware, so no QEMU test may close this.

        A two-disk QEMU run with `bootindex` would prove that we configured
        QEMU correctly, not that the user's machine starts from the target
        disk. The row must keep saying that out loud.
        """
        row = self._row_for_source("Omarchy #20178")
        self.assertIn("bios_grub", row[1])
        self.assertIn("Legacy/CSM", row[0])
        self.assertEqual(row[3].strip("`"), "not-covered")
        self.assertEqual(row[4], "—")
        self.assertIn("не наша властивість", row[2])
        self.assertIn("bootindex", row[2])

    def test_late_drm_handoff_is_not_claimed_covered_before_acceptance(self) -> None:
        """A guard against the known bad fix is `partial`, never `covered`.

        The property — hardware DRM is ready before SDDM — still needs QEMU
        late-KMS and physical acceptance. What changed is that the shipped
        system definitions now may not buy readiness with a fixed sleep, so the
        row has real evidence and the honest status is `partial`.
        """
        row = self._row_for_source("Omarchy #20059")
        self.assertIn("simpledrm", row[0])
        self.assertIn("GNU Shepherd", row[1])
        self.assertIn("bounded", row[1])
        self.assertEqual(row[3].strip("`"), "partial")
        self.assertIn(
            "tests/test_system_definitions_have_no_sleep.py::test_no_shipped_definition_waits_with_sleep",
            row[4],
        )
        self.assertIn("доводить", row[2], "the bound must stay written down")
        self.assertIn("не замінює", row[2])

    def test_rollcall_functional_checks_remain_partial_in_wsm_inventory(self) -> None:
        row = self._row_for_source("Omarchy rollcall (#20107)")
        self.assertIn("інвентаризації", row[0])
        self.assertIn("driver binding", row[1])
        self.assertIn("functional_tests", row[2])
        self.assertEqual(row[3].strip("`"), "partial")
        self.assertIn(
            "tests/test_hwcheck.py::test_inventory_separates_driver_binding_and_functional_tests",
            row[4],
        )
        self.assertIn(
            "tests/test_hwcheck.py::test_report_is_local_and_does_not_include_sensitive_identifiers",
            row[4],
        )
        self.assertIn("user-disabled skip", self.text)


    def test_boot_update_esp_identity_is_not_claimed_covered_without_updater(self) -> None:
        row = self._row_for_source("Omarchy #15435")
        self.assertIn("не-booted ESP", row[0])
        self.assertEqual(row[3].strip("`"), "out-of-scope")
        self.assertEqual(row[4], "—")

    def test_fixed_tmp_path_guard_is_only_partial_coverage_of_omarchy_19965(self) -> None:
        row = self._row_for_source("Omarchy #19965")
        self.assertEqual(row[3].strip("`"), "partial")
        self.assertIn("не доводить", row[2])
        self.assertIn(
            "tests/test_temp_path_containment.py::test_fixed_tmp_paths_exist_only_inside_the_guest_script",
            row[4],
        )

    def test_non_regular_lock_paths_are_out_of_scope_without_a_lock_manager(self) -> None:
        row = self._row_for_source("Omarchy #19998")
        self.assertIn("lock", row[0].lower())
        self.assertEqual(row[3].strip("`"), "out-of-scope")
        self.assertEqual(row[4], "—")

    def test_release_assets_are_read_back_before_a_draft_is_published(self) -> None:
        row = self._row_for_source("Omarchy #516")
        self.assertEqual(row[3].strip("`"), "covered")
        self.assertIn(
            "tests/test_verify_release_assets.py::test_valid_download_matches_local_bundle",
            row[4],
        )

    def test_register_class_names_are_unique(self) -> None:
        names = [row[0] for row in self.rows]
        self.assertEqual(len(names), len(set(names)), "duplicate regression class")

    def test_uncovered_rows_cite_nothing(self) -> None:
        for row in self.rows:
            status = row[3].strip("`")
            if status in EVIDENCE_STATUSES:
                continue
            self.assertEqual(
                row[4], "—", f"{row[0]}: {status} row must not cite evidence"
            )


class RegisterCensusTests(unittest.TestCase):
    """The published counts must come from the table, not from memory.

    The same defect happened in a sibling project: a census number lived in a
    test and in a document, the document fell two behind, and nobody saw it
    because the test was about something else. So the document states the
    counts and this test recomputes them.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = REGISTER.read_text(encoding="utf-8")
        cls.counts = {}
        for status in ("covered", "partial", "not-covered", "out-of-scope"):
            cls.counts[status] = 0
        for line in cls.text.splitlines():
            match = re.search(r"\|\s*`(covered|partial|not-covered|out-of-scope)`\s*\|", line)
            if match and line.startswith("| "):
                cls.counts[match.group(1)] += 1

    def test_census_total_matches_the_table(self) -> None:
        stated = re.search(r"із (\d+) класів у реєстрі", self.text)
        self.assertIsNotNone(stated, "the register must publish its census")
        self.assertEqual(int(stated.group(1)), sum(self.counts.values()))

    def test_census_per_status_matches_the_table(self) -> None:
        expected = {
            "закриті тестом": ("covered", r"(\d+) закриті тестом"),
            "закриті частково": ("partial", r"(\d+) закриті частково"),
            "не покритий": ("not-covered", r"(\d+) не покритий"),
            "позначені": ("out-of-scope", r"(\d+) позначені\s+`?out-of-scope`?"),
        }
        for phrase, (status, pattern) in expected.items():
            with self.subTest(status=status):
                match = re.search(pattern, self.text)
                self.assertIsNotNone(match, phrase)
                self.assertEqual(int(match.group(1)), self.counts[status], phrase)

    def test_the_census_is_not_empty(self) -> None:
        self.assertGreaterEqual(sum(self.counts.values()), 10)


if __name__ == "__main__":
    unittest.main()
