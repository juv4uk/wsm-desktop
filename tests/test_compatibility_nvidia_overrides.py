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
            elif char == "\\\\":
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

        self.assertIn('" -Dlibdir=lib"', mesa.replace('"', '"'))
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

    def test_fixed_wayland_package_wraps_the_pinned_egl_wayland_name(self) -> None:
        wayland = scheme_definition(PROFILE, "egl-wayland-fixed")

        self.assertIn("(with-fixed-mesa egl-wayland)", wayland)
        self.assertNotIn("(define egl-wayland2-fixed", PROFILE)


if __name__ == "__main__":
    unittest.main()
