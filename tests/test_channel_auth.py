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
        """The official installer is served by cgit, which refuses bots."""
        script = (ROOT / "scripts" / "install-guix.sh").read_text(encoding="utf-8")
        # Mentions in comments explain the history; only executable lines count.
        code = [
            line for line in script.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertFalse([line for line in code if "guix-install.sh" in line])
        self.assertIn("ftp.gnu.org", script)
        self.assertIn("guix-daemon", script)

class InstallerJobTests(unittest.TestCase):
    """An installer nobody runs is a claim, not a tool."""

    def setUp(self) -> None:
        self.text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_a_job_runs_the_repository_installer(self) -> None:
        self.assertIn("./scripts/install-guix.sh", self.text)

    def test_the_job_is_manual_only(self) -> None:
        """It installs a daemon on a throwaway runner; that must be deliberate."""
        self.assertIn("github.event_name == 'workflow_dispatch'", self.text)

    def test_the_job_proves_more_than_a_version_string(self) -> None:
        self.assertIn("guix-daemon", self.text)
        self.assertIn("build --dry-run", self.text)



if __name__ == "__main__":
    unittest.main()
