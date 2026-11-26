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
        self.assertTrue(all(step["status"] == "not-run" for step in payload["steps"]))
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

    def test_execute_without_acknowledgement_is_disabled(self) -> None:
        result = run_cli(
            "--install", "--execute", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB), "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)

    def test_matching_acknowledgement_still_cannot_enable_execute(self) -> None:
        result = run_cli(
            "--install", "--execute", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1", "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)

    def test_write_plan_creates_a_regular_preview_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            result = run_cli(
                "--install", "--target-disk", "/dev/nvme0n1",
                "--target-size-bytes", str(256 * GIB),
                "--acknowledge-disk", "/dev/nvme0n1",
                "--write-plan", str(output), "--quiet",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            plan = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(plan["schema"], "wsm-install-plan/1")
            self.assertEqual(plan["disk"], "/dev/nvme0n1")
            self.assertIn("APPLY disabled", result.stderr)

    def test_write_plan_refuses_device_nodes(self) -> None:
        result = run_cli(
            "--install", "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1",
            "--write-plan", "/dev/null", "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("write-plan.refused", result.stderr)

    def test_write_plan_refuses_symlink_to_a_device_node(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "plan.json"
            destination.symlink_to("/dev/null")
            result = run_cli(
                "--install", "--target-disk", "/dev/nvme0n1",
                "--target-size-bytes", str(256 * GIB),
                "--acknowledge-disk", "/dev/nvme0n1",
                "--write-plan", str(destination), "--quiet",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("write-plan.refused", result.stderr)
            self.assertTrue(destination.is_symlink())

    def test_write_plan_refuses_to_overwrite_the_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            original = FIXTURE.read_bytes()
            report.write_bytes(original)
            result = subprocess.run(
                [
                    sys.executable, "-m", "wsm_install",
                    "--preflight", "--dry-run",
                    "--report", str(report), "--backend", "guix",
                    "--install", "--target-disk", "/dev/nvme0n1",
                    "--target-size-bytes", str(256 * GIB),
                    "--acknowledge-disk", "/dev/nvme0n1",
                    "--write-plan", str(report), "--quiet",
                ],
                capture_output=True, text=True, check=False, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("write-plan.refused", result.stderr)
            self.assertEqual(report.read_bytes(), original)

    def test_guided_execute_is_rejected_before_interaction(self) -> None:
        result = run_cli("--guided", "--execute", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)

    def test_tui_execute_is_rejected_before_interaction(self) -> None:
        result = run_cli("--tui", "--execute", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)


if __name__ == "__main__":
    unittest.main()
