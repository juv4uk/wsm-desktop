# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks for the Guix system profiles.

These tests do not build a Guix image. They verify source structure and the
shell contract of the image builder using a fake Guix executable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ROOT / "systems"

DELIMITERS = "()[]"
CHAR_LITERAL = re.compile(r"#\\.")
BLOCK_COMMENT_START = "#|"
BLOCK_COMMENT_END = "|#"


def read_forms(text: str) -> list[str]:
    """Split Scheme source into top-level forms."""
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
    def _fake_guix(self, bin_dir: Path) -> None:
        fake_guix = bin_dir / "guix"
        fake_guix.write_text(
            "#!/bin/sh\n"
            "printf 'CALL' >> \"$WSM_TEST_GUIX_ARGS\"\n"
            "for argument in \"$@\"; do printf '|%s' \"$argument\" >> \"$WSM_TEST_GUIX_ARGS\"; done\n"
            "printf '\\nPWD=%s\\nGUIX_PACKAGE_PATH=%s\\n' \"$PWD\" \"$GUIX_PACKAGE_PATH\" >> \"$WSM_TEST_GUIX_ARGS\"\n"
            "if [ \"$1\" = '--version' ]; then echo 'guix (GNU Guix) 1.5.0-test'; exit 0; fi\n"
            "if [ \"$5\" = 'describe' ]; then\n"
            "  if [ \"${WSM_TEST_AUTH_DISABLED:-0}\" = '1' ]; then echo 'channel authentication disabled' >&2; fi\n"
            "  printf '%s\\n' '(list (channel (name \'guix\') (commit \'test\')))'\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$5\" = 'system' ] && [ \"$6\" = 'image' ]; then\n"
            "  root=\n"
            "  for argument in \"$@\"; do case \"$argument\" in --root=*) root=${argument#--root=} ;; esac; done\n"
            "  [ -n \"$root\" ] || exit 9\n"
            "  ln -s \"$WSM_TEST_IMAGE\" \"$root\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 8\n",
            encoding="utf-8",
        )
        fake_guix.chmod(0o755)

    def test_builder_uses_locked_channels_and_writes_manifest(self) -> None:
        script = ROOT / "scripts" / "build_iso.sh"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            bin_dir = temporary_root / "bin"
            output_dir = temporary_root / "out"
            bin_dir.mkdir()
            output_dir.mkdir()
            fake_image = temporary_root / "guix-store-image.iso"
            fake_image.write_bytes(b"synthetic test image bytes")
            args_log = temporary_root / "guix-args.txt"
            self._fake_guix(bin_dir)

            environment = os.environ.copy()
            environment["PATH"] = str(bin_dir) + os.pathsep + os.defpath
            environment["WSM_ISO_DIR"] = str(output_dir)
            environment["WSM_TEST_GUIX_ARGS"] = str(args_log)
            environment["WSM_TEST_IMAGE"] = str(fake_image)
            environment.pop("GUIX_PACKAGE_PATH", None)

            result = subprocess.run(
                ["/bin/sh", str(script)],
                cwd=temporary_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            expected = output_dir / "wsm-desktop-live.iso"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(expected.is_symlink())
            self.assertEqual(expected.resolve(), fake_image)

            calls = args_log.read_text(encoding="utf-8")
            lock = ROOT / "channels.lock.scm"
            self.assertIn(f"CALL|time-machine|-C|{lock}|--|describe|-f|channels", calls)
            self.assertIn(f"CALL|time-machine|-C|{lock}|--|system|image", calls)
            self.assertIn(f"--root={expected}", calls)
            self.assertIn("--no-grafts", calls)
            self.assertIn("--image-type=iso9660", calls)
            self.assertIn(f"GUIX_PACKAGE_PATH={ROOT}", calls)
            self.assertIn(f"PWD={ROOT}", calls)
            self.assertNotIn("--disable-authentication", calls)

            manifest_path = output_dir / "manifest.json"
            checksums_path = output_dir / "SHA256SUMS"
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(checksums_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["commit"], subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip())
            self.assertEqual(manifest["source"]["locked_guix_channel_commit"], re.search(
                r'\(commit\s+"([0-9a-f]{40})"\)',
                (ROOT / "channels.lock.scm").read_text(encoding="utf-8"),
            ).group(1))
            self.assertEqual(manifest["artifact"]["size_bytes"], fake_image.stat().st_size)
            self.assertEqual(
                manifest["artifact"]["sha256"],
                hashlib.sha256(fake_image.read_bytes()).hexdigest(),
            )
            self.assertIn("default", manifest["guix"]["authentication_policy"])

            checksum_entries = {}
            for line in checksums_path.read_text(encoding="utf-8").splitlines():
                digest, filename = line.split("  ", 1)
                checksum_entries[filename] = digest
            for filename, digest in checksum_entries.items():
                target = output_dir / filename
                if filename == expected.name:
                    target = expected
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)

            # A repeat must fail before calling Guix or replacing the previous link.
            previous_log = args_log.read_text(encoding="utf-8")
            again = subprocess.run(
                ["/bin/sh", str(script)],
                cwd=temporary_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(again.returncode, 3)
            self.assertEqual(args_log.read_text(encoding="utf-8"), previous_log)
            self.assertEqual(expected.resolve(), fake_image)

    def test_builder_fails_closed_when_channel_authentication_is_disabled(self) -> None:
        script = ROOT / "scripts" / "build_iso.sh"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            bin_dir = temporary_root / "bin"
            output_dir = temporary_root / "out"
            bin_dir.mkdir()
            output_dir.mkdir()
            fake_image = temporary_root / "guix-store-image.iso"
            fake_image.write_bytes(b"image must not be published")
            args_log = temporary_root / "guix-args.txt"
            self._fake_guix(bin_dir)

            environment = os.environ.copy()
            environment["PATH"] = str(bin_dir) + os.pathsep + os.defpath
            environment["WSM_ISO_DIR"] = str(output_dir)
            environment["WSM_TEST_GUIX_ARGS"] = str(args_log)
            environment["WSM_TEST_IMAGE"] = str(fake_image)
            environment["WSM_TEST_AUTH_DISABLED"] = "1"
            environment.pop("GUIX_PACKAGE_PATH", None)

            result = subprocess.run(
                ["/bin/sh", str(script)],
                cwd=temporary_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertIn("channel authentication is disabled", result.stderr)
            calls = args_log.read_text(encoding="utf-8")
            self.assertIn("CALL|time-machine|-C|", calls)
            self.assertNotIn("|--|system|image", calls)
            self.assertFalse((output_dir / "wsm-desktop-live.iso").exists())
            self.assertFalse((output_dir / "manifest.json").exists())

    def test_script_refuses_to_run_without_guix(self) -> None:
        text = (ROOT / "scripts" / "build_iso.sh").read_text(encoding="utf-8")
        self.assertIn("command -v guix", text)
        self.assertIn("exit 127", text)
        self.assertIn("time-machine -C", text)
        self.assertIn("--image-type=iso9660", text)


if __name__ == "__main__":
    unittest.main()
