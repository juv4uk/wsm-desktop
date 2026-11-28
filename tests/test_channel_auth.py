# SPDX-License-Identifier: LicenseRef-Volnist
"""The channel artefact reporter must report, not adjudicate."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_channel_auth import inspect  # noqa: E402


class InspectTests(unittest.TestCase):
    def make(self, directory: Path, *, metadata=True, authorizations=False, doc=True) -> None:
        if metadata:
            (directory / ".guix-channel").write_text("(channel)\n", encoding="utf-8")
        if authorizations:
            (directory / ".guix-authorizations").write_text("()\n", encoding="utf-8")
        if doc:
            (directory / "docs").mkdir(exist_ok=True)
            (directory / "docs" / "GUIX-CHANNEL.md").write_text("# канал\n", encoding="utf-8")

    def test_missing_authorizations_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory)
            state = inspect(directory)
        self.assertIn("authorizations", state["missing"])

    def test_missing_keyring_branch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory, authorizations=True)
            state = inspect(directory)
        self.assertIn("keyring-branch", state["missing"])

    def test_authentication_is_never_claimed(self) -> None:
        """Only guix git authenticate can decide; a file listing cannot."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory, authorizations=True)
            state = inspect(directory)
        self.assertIsInstance(state["authenticated"], str)
        self.assertIn("unknown", state["authenticated"])

    def test_the_repository_reports_without_failing(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_channel_auth.py", "."],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authenticated: unknown by design", result.stdout)

    def test_install_script_does_not_depend_on_savannah(self) -> None:
        """The binary-tarball bootstrap avoids the flaky Savannah cgit route."""
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        code = [
            line for line in script.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertFalse([line for line in code if "guix-install.sh" in line])
        self.assertIn("ftp.gnu.org", script)
        self.assertIn("guix-daemon", script)

    def test_binary_tarball_signature_is_verified_before_extract(self) -> None:
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        self.assertIn('wget -q -O "$WORKDIR/$TARBALL.sig" "$URL.sig"', script)
        self.assertIn("--verify", script)
        self.assertIn("A28BF40C3E551372662D14F741AAE7DCCA3D8351", script)
        self.assertIn("https://codeberg.org/efraim.gpg", script)
        self.assertLess(script.index("--verify"), script.index("tar --warning=no-timestamp -xf"))

    def test_installer_refuses_existing_guix_store_and_profile(self) -> None:
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        self.assertIn("[ -e /gnu ] || [ -e /var/guix ]", script)
        self.assertNotIn('sudo mv "$WORKDIR/gnu/"* /gnu/ 2>/dev/null || true', script)
        self.assertNotIn('sudo mv "$WORKDIR/var/guix/"* /var/guix/ 2>/dev/null || true', script)

    def test_chroot_is_not_disabled_unless_explicitly_requested(self) -> None:
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        self.assertIn("GUIX_ALLOW_UNSANDBOXED_BUILDS", script)
        self.assertIn("DAEMON_ARGS+=(--disable-chroot)", script)
        self.assertIn("disposable runner", script)

    def test_custom_prefix_creates_bin_directory(self) -> None:
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        self.assertIn('as_root mkdir -p "$GUIX_PREFIX/bin"', script)


if __name__ == "__main__":
    unittest.main()
