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
        row = self._row_for_source("Omarchy #20178")
        self.assertIn("bios_grub", row[1])
        self.assertIn("Legacy/CSM", row[0])
        self.assertEqual(row[3].strip("`"), "not-covered")
        self.assertEqual(row[4], "—")

    def test_late_drm_handoff_is_not_claimed_covered_before_acceptance(self) -> None:
        row = self._row_for_source("Omarchy #20059")
        self.assertIn("simpledrm", row[0])
        self.assertIn("GNU Shepherd", row[1])
        self.assertIn("bounded", row[1])
        self.assertEqual(row[3].strip("`"), "not-covered")
        self.assertEqual(row[4], "—")
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


if __name__ == "__main__":
    unittest.main()
