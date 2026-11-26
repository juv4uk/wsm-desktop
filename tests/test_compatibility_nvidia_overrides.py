# SPDX-License-Identifier: LicenseRef-Volnist
"""Source-level guard for overrides against the pinned Nonguix NVIDIA 580 graph.

This test catches accidental replacement of an inherited input with a similarly
named package that is not part of the pinned driver graph. It does not replace
Guix evaluation or a real Compatibility ISO build.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = (ROOT / "systems" / "live-compat.scm").read_text(encoding="utf-8")
LOCK = (ROOT / "channels" / "compatibility.lock.scm").read_text(encoding="utf-8")


def scheme_definition(source: str, name: str) -> str:
    """Return one top-level Scheme define form, balancing parentheses safely."""
    marker = f"(define {name}"
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"Scheme definition not found: {name}")

    depth = 0
    in_string = False
    escaped = False
    in_comment = False

    for index in range(start, len(source)):
        char = source[index]

        if in_comment:
            if char == "\n":
                in_comment = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == ";":
            in_comment = True
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]

    raise AssertionError(f"Unbalanced Scheme form: {name}")


class CompatibilityNvidiaOverrideTests(unittest.TestCase):
    def test_profile_header_separates_build_evidence_from_physical_acceptance(self) -> None:
        header = PROFILE.split("(use-modules", 1)[0]
        self.assertIn("окремий opt-in Compatibility", header)
        self.assertIn("Nonguix", header)
        self.assertIn("PCI ID 10de:1c82", header)
        self.assertIn("локально зібрано в", header)
        self.assertIn("QEMU TCG BIOS boot", header)
        self.assertIn("ранній Guile init segfault", header)
        self.assertIn("Physical H170 / GTX 1050 Ti binding", header)
        self.assertIn("NOT RUN; потрібен окремий boot", header)
        self.assertIn("не є загальним твердженням про всі Pascal GPU", header)
        self.assertIn("Жодних тверджень про підтримку GTX 1050 Ti на реальному обладнанні", header)
        self.assertNotIn("Guix evaluation: NOT RUN", header)
        self.assertNotIn("Compatibility package closure та image build: NOT RUN", header)
        self.assertNotIn("QEMU BIOS/UEFI boot: NOT RUN", header)
        self.assertNotIn("пропрієтарного firmware чи Nonguix", header)

    def test_pascal_driver_selection_is_scoped_to_the_exact_1050_ti_id(self) -> None:
        header = PROFILE.split("(use-modules", 1)[0]
        self.assertIn("580.196.11", header)
        self.assertIn("595.45.04", header)
        self.assertIn("ID 1C82 відсутній", header)
        self.assertIn("не доводить, що pinned", header)
        self.assertNotIn("590+ GPU не розпізнає", header)

    def test_override_is_bound_to_the_reviewed_compatibility_lock(self) -> None:
        self.assertIn(
            '(name \'nonguix)',
            LOCK,
        )
        self.assertIn(
            '(commit "6b8897cd6f3223b158c070cdc9cc638279f8c337")',
            LOCK,
        )

    def test_mesa_runtime_closure_uses_the_fixed_libglvnd_variant(self) -> None:
        mesa = scheme_definition(PROFILE, "mesa-for-nvda-fixed")

        self.assertIn('"-Dlibdir=lib"', mesa)
        self.assertIn("(package-propagated-inputs mesa-for-nvda)", mesa)
        self.assertIn(
            '(replace "libglvnd" libglvnd-for-nvda-fixed)',
            mesa,
        )

    def test_580_driver_replaces_the_egl_wayland_input_from_its_parent(self) -> None:
        driver = scheme_definition(PROFILE, "nvidia-driver-580-fixed")

        self.assertIn('(replace "egl-wayland" egl-wayland-fixed)', driver)
        self.assertIn('(replace "egl-gbm" egl-gbm-fixed)', driver)
        self.assertIn('(replace "egl-x11" egl-x11-fixed)', driver)
        self.assertIn('(replace "mesa" mesa-for-nvda-fixed)', driver)

    def test_egl_wayland_binding_is_imported_from_the_pinned_xorg_module(self) -> None:
        imports = PROFILE.split("(use-service-modules", 1)[0]
        self.assertIn("(gnu packages xorg)", imports)
        self.assertIn(
            "(define egl-wayland-fixed (with-fixed-mesa egl-wayland))",
            PROFILE,
        )

    def test_fixed_wayland_package_wraps_the_pinned_egl_wayland_name(self) -> None:
        wayland = scheme_definition(PROFILE, "egl-wayland-fixed")

        self.assertIn("(with-fixed-mesa egl-wayland)", wayland)
        self.assertNotIn("(define egl-wayland2-fixed", PROFILE)


if __name__ == "__main__":
    unittest.main()
