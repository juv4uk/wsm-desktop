# SPDX-License-Identifier: LicenseRef-Volnist
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


class KnownPitfallTests(unittest.TestCase):
    def test_sddm_is_not_set_to_wayland(self) -> None:
        """Guix bug#68939: display-server "wayland" leaves a black screen.

        The value is documented but the service does not support it; a later
        patch makes the service ignore it. Setting it would produce a system
        that boots to a blank display and looks like a broken image.
        """
        text = profile("desktop.scm")
        self.assertNotIn('(display-server "wayland")', text)

    def test_bluetooth_is_auto_enabled(self) -> None:
        """A Bluetooth mouse cannot be paired by a user who has no mouse.

        This was #f with a "radio nobody asked for" argument, which did not
        survive contact with a keyboard that has no cable.
        """
        text = profile("desktop.scm")
        self.assertIn("(auto-enable? #t)", text)


class SourceResolutionTests(unittest.TestCase):
    def test_live_profile_does_not_use_a_relative_include(self) -> None:
        """`include` with a relative path depends on the working directory."""
        text = profile("live.scm")
        self.assertNotIn('(include "desktop.scm")', text)
        self.assertIn("current-filename", text)

    def test_package_source_excludes_vcs_metadata(self) -> None:
        """Without select? the store copy would embed .git and vary per clone."""
        text = (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8")
        self.assertIn("#:select?", text)
        for skipped in ("/.git", "/__pycache__", "/build"):
            with self.subTest(skip=skipped):
                self.assertIn(skipped, text)


class LiveProfileTests(unittest.TestCase):
    def test_live_profile_inherits_the_desktop_profile(self) -> None:
        text = profile("live.scm")
        self.assertIn('"/desktop.scm"', text)
        self.assertIn("(inherit base-os)", text)

    def test_live_profile_installs_the_wsm_tools(self) -> None:
        self.assertIn("wsm-tools", profile("live.scm"))
        self.assertIn("wsm-tools", (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8"))


class PerformanceServicesTests(unittest.TestCase):
    def test_desktop_profile_pulls_the_performance_services(self) -> None:
        self.assertIn("%wsm-performance-services", profile("desktop.scm"))
        self.assertIn("(wsm systems performance)", profile("desktop.scm"))

    def test_performance_module_lives_at_its_module_path(self) -> None:
        """(wsm systems performance) must be wsm/systems/performance.scm."""
        self.assertTrue((ROOT / "wsm" / "systems" / "performance.scm").is_file())

    def test_zram_uses_zstd_and_no_deprecated_priority(self) -> None:
        text = (ROOT / "wsm" / "systems" / "performance.scm").read_text(encoding="utf-8")
        self.assertIn("(compression-algorithm 'zstd)", text)
        # -1 is deprecated upstream; leaving the field out keeps the default.
        self.assertNotIn("(priority -1)", text)

    def test_no_security_mitigations_are_disabled(self) -> None:
        """Speed is never bought by switching mitigations off."""
        for name in ("desktop.scm", "live.scm", "compatibility.scm"):
            with self.subTest(profile=name):
                self.assertNotIn("mitigations=off", profile(name))


class DesktopCompletenessTests(unittest.TestCase):
    """What separates a booting system from one somebody can work on."""

    def test_printing_is_configured(self) -> None:
        text = profile("desktop.scm")
        self.assertIn("cups-service-type", text)
        # Without the web interface there is no way to add a network printer:
        # Guix configuration files are read-only, so cupsctl cannot help.
        self.assertIn("(web-interface? #t)", text)

    def test_a4_is_the_default_paper(self) -> None:
        self.assertIn('(default-paper-size "A4")', profile("desktop.scm"))

    def test_no_system_wide_pulseaudio(self) -> None:
        """PipeWire serves the PulseAudio protocol in the user session.

        A system daemon as well means two stacks fighting for one device.
        """
        self.assertNotIn("pulseaudio-service-type", profile("desktop.scm"))


class PublishedIsoTests(unittest.TestCase):
    """Every live profile must carry the acceptance marker.

    The published 0.1.0-rc2-live-iso image was checked byte for byte: it contains
    wsm-install, but no WSM_LIVE_READY anywhere. The profile that built it
    (systems/live-iso.scm) had no marker service, so no acceptance check could
    ever have passed on that image.
    """

    def test_every_live_profile_prints_the_marker(self) -> None:
        for name in ("live.scm", "live-minimal.scm", "live-iso.scm"):
            with self.subTest(profile=name):
                self.assertIn("WSM_LIVE_READY", profile(name))

    def test_every_live_profile_registers_the_marker_service(self) -> None:
        for name in ("live.scm", "live-minimal.scm", "live-iso.scm"):
            with self.subTest(profile=name):
                self.assertIn("wsm-live-ready-marker", profile(name))

    def test_the_iso_profile_ships_the_installer_tools(self) -> None:
        """The image must contain what it is supposed to install with."""
        self.assertIn("wsm-live-tools", profile("live-iso.scm"))


class AudioConflictTests(unittest.TestCase):
    """The published image shipped both PipeWire and PulseAudio. That was a bug.

    Byte-level inspection of wsm-desktop-kde-hardened-20261125.iso found
    pipewire-1.6.8 and pulseaudio-17.0 in the same store. #262 removed the
    system-wide PulseAudio service for exactly this reason; this test keeps it
    from coming back through the desktop profile.
    """

    def test_desktop_profile_does_not_start_system_pulseaudio(self) -> None:
        self.assertNotIn("pulseaudio-service-type", profile("desktop.scm"))

    def test_live_profiles_do_not_start_system_pulseaudio(self) -> None:
        for name in ("live.scm", "live-minimal.scm", "live-iso.scm"):
            with self.subTest(profile=name):
                self.assertNotIn("(service pulseaudio-service-type)", profile(name))


class MinimalLiveTests(unittest.TestCase):
    """A second live image, for hardware that cannot run a graphical installer."""

    def test_minimal_live_has_no_graphical_stack(self) -> None:
        text = profile("live-minimal.scm")
        for forbidden in ("plasma-desktop-service-type", "sddm-service-type",
                          "gnome-desktop-service-type", "calamares"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_minimal_live_carries_the_wsm_tools(self) -> None:
        text = profile("live-minimal.scm")
        self.assertIn("(wsm packages wsm)", text)
        self.assertIn("wsm-tools", text)

    def test_minimal_live_prints_the_same_acceptance_marker(self) -> None:
        """Acceptance is one contract; a second image is not exempt from it."""
        text = profile("live-minimal.scm")
        self.assertIn("WSM_LIVE_READY", text)
        self.assertIn("console=ttyS0", text)

    def test_minimal_live_has_no_audio_printing_or_bluetooth(self) -> None:
        text = profile("live-minimal.scm")
        for absent in ("cups-service-type", "bluetooth-service-type",
                       "pipewire", "pulseaudio"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, text)


class HomeEnvironmentTests(unittest.TestCase):
    """Sound is a per-user service in Guix; a system-wide attempt gives two stacks."""

    def test_home_profile_uses_pipewire(self) -> None:
        text = (ROOT / "systems" / "home.scm").read_text(encoding="utf-8")
        self.assertIn("(gnu home services sound)", text)
        self.assertIn("home-pipewire-service-type", text)

    def test_pulseaudio_emulation_stays_enabled(self) -> None:
        """Without it, Plasma's volume applet and most apps see no server."""
        text = (ROOT / "systems" / "home.scm").read_text(encoding="utf-8")
        self.assertNotIn("(enable-pulseaudio? #f)", text)

    def test_home_profile_does_not_start_a_second_audio_daemon(self) -> None:
        text = (ROOT / "systems" / "home.scm").read_text(encoding="utf-8")
        self.assertNotIn("home-pulseaudio-rtp", text)
        self.assertNotIn("pulseaudio-service-type", text)


class CompatibilityProfileTests(unittest.TestCase):
    def test_compatibility_profile_uses_the_nonguix_transformation(self) -> None:
        text = profile("compatibility.scm")
        self.assertIn("nonguix-transformation-nvidia", text)
        self.assertIn("#:driver nvda-580", text)
        # Without this the Xorg session never learns about the nvidia module.
        self.assertIn("#:configure-xorg? sddm-service-type", text)

    def test_compatibility_profile_blacklists_nouveau(self) -> None:
        self.assertIn("modprobe.blacklist=nouveau", profile("compatibility.scm"))

    def test_free_profiles_do_not_import_nonguix(self) -> None:
        """A single Nonguix import in desktop.scm would poison the Free profile."""
        for name in ("desktop.scm", "live.scm"):
            code = "\n".join(
                line for line in profile(name).splitlines()
                if not line.strip().startswith(";")
            )
            with self.subTest(profile=name):
                self.assertNotIn("nonguix", code.lower())
                self.assertNotIn("nongnu", code.lower())

    def test_compatibility_profile_is_not_reachable_from_the_live_image(self) -> None:
        """The live image stays Free; Compatibility is a deliberate separate build."""
        self.assertNotIn("compatibility.scm", profile("live.scm"))
class LiveIsoSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = profile("live-iso.scm")
        match = re.search(r"\(users\s+\(cons\s+\(user-account([\s\S]*?)%base-user-accounts", cls.text)
        if match is None:
            raise AssertionError("live ISO must declare its dedicated unprivileged live account")
        cls.user = match.group(1)

    def test_live_account_has_no_reusable_or_empty_password(self) -> None:
        self.assertIn("(password #f)", self.user)
        self.assertNotIn('(password "wsm")', self.user)
        self.assertNotIn('"wheel"', self.user)
        self.assertIn('(auto-login-user "wsm")', self.text)
        self.assertIn('(auto-login-session "plasma")', self.text)

    def test_console_login_rejects_empty_passwords(self) -> None:
        self.assertIn("(use-service-modules base ", self.text)
        self.assertIn("(login-service-type config =>", self.text)
        self.assertIn("(allow-empty-passwords? #f)", self.text)

    def test_live_image_does_not_enable_passwordless_sudo(self) -> None:
        self.assertNotIn("NOPASSWD", self.text)
        self.assertNotIn("sudoers", self.text.lower())
        self.assertNotIn('"wheel"', self.user)


class IsoScriptTests(unittest.TestCase):
    def _fake_guix(self, bin_dir: Path) -> None:
        fake_guix = bin_dir / "guix"
        fake_guix.write_text(
            """#!/bin/sh
printf 'CALL' >> "$WSM_TEST_GUIX_ARGS"
for argument in "$@"; do printf '|%s' "$argument" >> "$WSM_TEST_GUIX_ARGS"; done
printf '\\nPWD=%s\\n' "$PWD" >> "$WSM_TEST_GUIX_ARGS"
root=
case " $* " in
    *" -- --version "*) echo 'guix (GNU Guix) 1.5.0-pinned'; exit 0 ;;
    *" describe -f channels "*)
        if [ "$WSM_TEST_AUTH_DISABLED" = '1' ]; then
            echo 'channel authentication disabled' >&2
        fi
        printf '%s\\n' '(list (channel (name guix) (commit test)))'
        exit 0 ;;
    *" system image "*)
        for argument in "$@"; do
            case "$argument" in --root=*) root=${argument#--root=} ;; esac
        done
        [ -n "$root" ] || exit 9
        ln -s "$WSM_TEST_IMAGE" "$root"
        exit 0 ;;
esac
exit 8
""",
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
            self.assertIn(f"CALL|time-machine|-C|{lock}|-L|{ROOT}|--|describe|-f|channels", calls)
            self.assertIn(f"CALL|time-machine|-C|{lock}|-L|{ROOT}|--|system|image", calls)
            self.assertIn(f"--root={expected}", calls)
            self.assertIn("--no-grafts", calls)
            self.assertIn("--image-type=iso9660", calls)
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
            self.assertEqual(manifest["guix"]["locked_version"], "guix (GNU Guix) 1.5.0-pinned")

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
