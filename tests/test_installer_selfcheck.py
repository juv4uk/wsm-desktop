# SPDX-License-Identifier: LicenseRef-Volnist
"""Boot is not installation: the image must prove it ships a working installer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qemu_boot_smoke import main  # noqa: E402


class InstallerMarkerTests(unittest.TestCase):
    def test_dry_run_never_claims_installer_execution(self) -> None:
        """Nothing ran, so nothing is proven."""
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "live.iso"
            iso.write_bytes(b"placeholder")
            result = main(["--iso", str(iso), "--dry-run", "--installer-marker", "WSM_INSTALLER_OK"])
        self.assertEqual(result, 0)

    def test_the_profile_announces_the_installer_result(self) -> None:
        profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.assertIn("WSM_INSTALLER_OK", profile)
        self.assertIn("WSM_INSTALLER_FAIL", profile)
        self.assertIn("wsm-install", profile)

    def test_the_selfcheck_runs_the_entrypoint_not_a_copy(self) -> None:
        """A marker printed without running the entrypoint would prove nothing."""
        profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")
        self.assertIn("/run/current-system/profile/bin/wsm-install", profile)
        self.assertIn("system*", profile)

    def test_acceptance_requires_the_installer_marker(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("--installer-marker WSM_INSTALLER_OK"), 2)
        self.assertIn("installer did not run in the guest", workflow)

    def test_manifest_records_installer_acceptance(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn('"installer":"pass"', workflow)

class SelfcheckEnvironmentTests(unittest.TestCase):
    """A missing python3 on the daemon PATH would look like a broken installer."""

    def setUp(self) -> None:
        self.profile = (ROOT / "systems" / "live-minimal.scm").read_text(encoding="utf-8")

    def test_the_selfcheck_pins_its_own_path(self) -> None:
        self.assertIn('(setenv "PATH"', self.profile)
        self.assertIn("/run/current-system/profile/bin", self.profile)

    def test_the_path_is_set_before_the_entrypoint_runs(self) -> None:
        self.assertLess(self.profile.index('(setenv "PATH"'),
                        self.profile.index("/run/current-system/profile/bin/wsm-install"))



if __name__ == "__main__":
    unittest.main()
