# SPDX-License-Identifier: LicenseRef-Volnist
"""The install path must be reachable, and must not run by accident."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


def run_cli(*extra: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "report.json"
        report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "wsm_install", "--preflight", "--dry-run",
             "--report", str(report), "--backend", "guix", *extra],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )


class InstallModeTests(unittest.TestCase):
    def test_dry_run_plans_without_executing(self) -> None:
        result = run_cli(
            "--install", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1", "--quiet",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(
            payload["target_size_source"],
            "user-supplied planning estimate; not read from the block device",
        )
        self.assertTrue(all(step["status"] == "skipped" for step in payload["steps"]))
        self.assertEqual(payload["handoff"][:3], ["guix", "system", "init"])

    def test_install_without_disk_is_refused(self) -> None:
        result = run_cli("--install", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target-disk", result.stderr)

    def test_install_without_size_is_refused(self) -> None:
        """Size is how a replaced disk is caught, so it cannot be omitted."""
        result = run_cli("--install", "--target-disk", "/dev/nvme0n1", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target-size-bytes", result.stderr)

    def test_install_without_acknowledgement_is_refused(self) -> None:
        result = run_cli(
            "--install", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB), "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("acknowledgement", result.stderr)

    def test_partition_path_is_refused(self) -> None:
        result = run_cli(
            "--install", "--target-disk", "/dev/nvme0n1p1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1p1", "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("disk.path", result.stderr)

    def test_execute_without_acknowledgement_never_reaches_a_command(self) -> None:
        """The dangerous flag alone must not be enough."""
        result = run_cli(
            "--install", "--execute", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB), "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("acknowledgement", result.stderr)

    def test_execute_with_valid_disk_acknowledgement_is_still_disabled(self) -> None:
        """Matching a path string does not authorize a real disk write."""
        result = run_cli(
            "--install", "--execute",
            "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("execute.apply-disabled", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
