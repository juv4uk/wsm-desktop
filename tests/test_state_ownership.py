# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks that the state-ownership contract matches the shipped profile.

The contract in docs/STATELESS-CONFIGURATION.md is only worth something if it
stays true. These tests do not prove the system behaves correctly — they stop
the document from drifting away from systems/desktop.scm, and they stop a path
from being forgotten when the profile changes.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "STATELESS-CONFIGURATION.md"
PROFILE = ROOT / "systems" / "desktop.scm"

REQUIRED_PATHS = ("/gnu/store", "/etc", "/usr", "/var/lib", "/home", "/run", "/tmp")

# Phrases that make a rollback answer explicit rather than implied.
ROLLBACK_ANSWERS = ("повертається", "не повертається", "зникає", "відтворюється")


def contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def ownership_rows() -> list[list[str]]:
    """Return the ownership table as a list of cell lists, header excluded."""
    rows: list[list[str]] = []
    inside = False
    for line in contract_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            inside = inside and False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if "Клас" in cells[0]:
            inside = True
            continue
        if not inside or set(stripped) <= set("|- "):
            continue
        rows.append(cells)
    return rows


class ContractShapeTests(unittest.TestCase):
    def test_contract_exists_and_has_ownership_table(self) -> None:
        self.assertTrue(CONTRACT.is_file(), "contract document is missing")
        rows = ownership_rows()
        self.assertGreaterEqual(len(rows), 4, "ownership table has too few rows")

    def test_every_required_path_is_covered(self) -> None:
        """Paths must appear in the ownership table, not merely somewhere in prose."""
        table = " ".join(" ".join(row) for row in ownership_rows())
        for path in REQUIRED_PATHS:
            with self.subTest(path=path):
                # Whole path only: "/tmp" must not match "/tmpdir".
                pattern = rf"(?<![\w/]){re.escape(path)}(?![\w-])"
                self.assertRegex(
                    table, pattern, f"{path} has no row in the ownership table"
                )

    def test_each_class_states_what_rollback_does(self) -> None:
        for row in ownership_rows():
            with self.subTest(row=row[0]):
                joined = " ".join(row).lower()
                self.assertTrue(
                    any(answer in joined for answer in ROLLBACK_ANSWERS),
                    f"row {row[0]!r} does not say what a generation rollback does",
                )

    def test_data_loss_boundary_is_stated(self) -> None:
        """A rollback returns the system, not the data. That must be explicit."""
        lowered = contract_text().lower()
        self.assertIn("не повертає", lowered)
        self.assertIn("дані", lowered)


class ProfileMatchesContractTests(unittest.TestCase):
    def test_profile_does_not_mount_a_writable_usr_or_var(self) -> None:
        """A separate /usr or /var mount would invalidate the ownership table."""
        text = PROFILE.read_text(encoding="utf-8")
        mounts = re.findall(r'\(mount-point "([^"]+)"\)', text)
        for mount in mounts:
            with self.subTest(mount=mount):
                self.assertFalse(
                    mount == "/usr" or mount == "/var" or mount.startswith("/var/"),
                    f"profile mounts {mount}, which the contract does not cover",
                )

    def test_profile_mounts_root_and_efi_only(self) -> None:
        text = PROFILE.read_text(encoding="utf-8")
        mounts = set(re.findall(r'\(mount-point "([^"]+)"\)', text))
        self.assertEqual(mounts, {"/", "/boot/efi"})


if __name__ == "__main__":
    unittest.main()
