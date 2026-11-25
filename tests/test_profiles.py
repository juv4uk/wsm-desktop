# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks the profile matrix in systems/profiles.json.

Deliverable 5 of #149 is "prove that Desktop does not pull Developer". Without
Guix nothing can be measured, so the matrix is the contract and these tests keep
it honest: a component may not appear in a profile that should not have it, and
a nonfree component may not appear in a free profile at all.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "systems" / "profiles.json"
DESKTOP_PROFILE = ROOT / "systems" / "desktop.scm"

FREE_PROFILES = ("desktop", "developer", "creator")


def matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def components(profile: dict) -> set[str]:
    names = set(profile.get("system_packages", [])) | set(profile.get("user_packages", []))
    names |= {component["name"] for component in profile.get("components", [])}
    return names


class MatrixShapeTests(unittest.TestCase):
    def test_every_profile_declares_what_it_needs(self) -> None:
        for name, profile in matrix()["profiles"].items():
            with self.subTest(profile=name):
                for field in ("summary", "extends", "license", "hardware"):
                    self.assertIn(field, profile, f"{name} has no {field}")

    def test_extends_points_at_known_profiles(self) -> None:
        profiles = matrix()["profiles"]
        for name, profile in profiles.items():
            for parent in profile["extends"]:
                with self.subTest(profile=name, parent=parent):
                    self.assertIn(parent, profiles)

    def test_no_component_is_declared_twice_across_profiles(self) -> None:
        seen: dict[str, str] = {}
        for name, profile in matrix()["profiles"].items():
            for component in components(profile):
                with self.subTest(component=component):
                    self.assertNotIn(
                        component,
                        seen,
                        f"{component} is declared in both {seen.get(component)} and {name}",
                    )
                    seen[component] = name


class IsolationTests(unittest.TestCase):
    def test_desktop_does_not_pull_developer_or_creator(self) -> None:
        profiles = matrix()["profiles"]
        desktop = components(profiles["desktop"])
        for other in ("developer", "creator"):
            overlap = desktop & components(profiles[other])
            self.assertEqual(overlap, set(), f"desktop overlaps {other}: {sorted(overlap)}")

    def test_compatibility_is_not_part_of_any_free_profile(self) -> None:
        profiles = matrix()["profiles"]
        nonfree = components(profiles["compatibility"])
        for name in FREE_PROFILES:
            overlap = nonfree & components(profiles[name])
            self.assertEqual(overlap, set(), f"{name} contains nonfree {sorted(overlap)}")
        for name in FREE_PROFILES:
            self.assertEqual(profiles[name]["license"], "free")

    def test_every_nonfree_component_states_licence_and_redistribution(self) -> None:
        for component in matrix()["profiles"]["compatibility"]["components"]:
            with self.subTest(component=component["name"]):
                self.assertTrue(component.get("licence"))
                self.assertTrue(component.get("redistribution"))
                self.assertTrue(component.get("reason"))


class DesktopProfileConsistencyTests(unittest.TestCase):
    def test_fonts_in_the_profile_are_the_ones_the_matrix_lists(self) -> None:
        """The matrix and systems/desktop.scm must not drift apart."""
        text = DESKTOP_PROFILE.read_text(encoding="utf-8")
        declared = set(matrix()["profiles"]["desktop"]["system_packages"])
        fonts = {name for name in declared if name.startswith("font-")}
        self.assertTrue(fonts, "matrix lists no fonts")
        for font in fonts:
            with self.subTest(font=font):
                self.assertIn(font, text)


if __name__ == "__main__":
    unittest.main()
