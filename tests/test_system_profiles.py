# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for the Guix system profiles.

These tests do not build anything. Without Guix they cannot: the profiles are
declarative Scheme that only Guix can evaluate. What they do check is that each
file is a sequence of complete s-expressions (so it cannot be half-written or
truncated), and that the properties the profiles claim to have are actually
written in them.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ROOT / "systems"

DELIMITERS = "()[]"
CHAR_LITERAL = re.compile(r"#\\.")
BLOCK_COMMENT_START = "#|"
BLOCK_COMMENT_END = "|#"


def read_forms(text: str) -> list[str]:
    """Split Scheme source into top-level forms.

    Raises ValueError on an unbalanced file, which is what a truncated write
    looks like. Handles line comments, nested block comments, strings with
    escapes and character literals such as #\\( -- all of which contain
    characters that would otherwise be mistaken for structure.
    """
    forms: list[str] = []
    depth = 0
    start: int | None = None
    index = 0
    length = len(text)
    block_depth = 0

    while index < length:
        if block_depth:
            if text.startswith(BLOCK_COMMENT_START, index):
                block_depth += 1
                index += 2
                continue
            if text.startswith(BLOCK_COMMENT_END, index):
                block_depth -= 1
                index += 2
                continue
            index += 1
            continue

        character = text[index]

        if text.startswith(BLOCK_COMMENT_START, index):
            block_depth = 1
            index += 2
            continue

        if character == ";":
            newline = text.find("\n", index)
            index = length if newline == -1 else newline + 1
            continue

        if character == '"':
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                index += 1
            else:
                raise ValueError("unterminated string literal")
            continue

        if text.startswith("#\\", index):
            match = CHAR_LITERAL.match(text, index)
            if match:
                index = match.end()
                continue

        if character in DELIMITERS:
            if character in "([":
                if depth == 0:
                    start = index
                depth += 1
            else:
                depth -= 1
                if depth < 0:
                    raise ValueError(f"unexpected closing delimiter at offset {index}")
                if depth == 0 and start is not None:
                    forms.append(text[start : index + 1])
                    start = None
        index += 1

    if block_depth:
        raise ValueError("unterminated block comment")
    if depth != 0:
        raise ValueError(f"unbalanced parentheses: {depth} left open")
    return forms


def profile(name: str) -> str:
    return (SYSTEMS / name).read_text(encoding="utf-8")


class SchemeReadabilityTests(unittest.TestCase):
    def test_every_profile_is_a_sequence_of_complete_forms(self) -> None:
        files = sorted(SYSTEMS.glob("*.scm")) + sorted((ROOT / "wsm").rglob("*.scm"))
        self.assertTrue(files, "no scheme files found")
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                forms = read_forms(path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(forms), 1)

    def test_truncated_file_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_forms("(operating-system\n  (host-name \"wsm\")\n")

    def test_character_literal_does_not_break_reading(self) -> None:
        forms = read_forms("(keyboard-layout (keyboard-layout \"us\") #\\( )")
        self.assertEqual(len(forms), 1)


class DesktopProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = profile("desktop.scm")

    def test_has_exactly_one_display_manager(self) -> None:
        self.assertIn("sddm-service-type", self.text)
        # GDM comes in through %desktop-services; two managers fight over one seat.
        self.assertIn("(delete gdm-service-type)", self.text)

    def test_has_a_desktop_environment(self) -> None:
        self.assertIn("plasma-desktop-service-type", self.text)

    def test_has_cyrillic_fonts(self) -> None:
        for font in ("font-dejavu", "font-liberation", "font-noto"):
            with self.subTest(font=font):
                self.assertIn(font, self.text)

    def test_has_ukrainian_locale(self) -> None:
        self.assertIn("uk_UA.utf8", self.text)

    def test_free_profile_does_not_reference_nonguix(self) -> None:
        """Comments may mention Nonguix; the code must not depend on it."""
        for name in ("desktop.scm", "live.scm"):
            with self.subTest(profile=name):
                code = re.sub(r"(?m);.*$", "", profile(name)).lower()
                self.assertNotIn("nonguix", code)
                self.assertNotIn("channel", code)


class LiveProfileTests(unittest.TestCase):
    def test_live_profile_inherits_the_desktop_profile(self) -> None:
        text = profile("live.scm")
        self.assertIn('(include "desktop.scm")', text)
        self.assertIn("(inherit base-os)", text)

    def test_live_profile_installs_the_wsm_tools(self) -> None:
        self.assertIn("wsm-tools", profile("live.scm"))
        self.assertIn("wsm-tools", (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8"))


class IsoScriptTests(unittest.TestCase):
    def test_script_refuses_to_run_without_guix(self) -> None:
        text = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
        self.assertIn("command -v guix", text)
        self.assertIn("exit 127", text)
        self.assertIn("--image-type=iso9660", text)


if __name__ == "__main__":
    unittest.main()
