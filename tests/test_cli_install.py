# SPDX-License-Identifier: LicenseRef-Volnist
"""The installer CLI can plan and preview, but cannot perform APPLY."""

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
            [
                sys.executable,
                "-m",
                "wsm_install",
                "--preflight",
                "--dry-run",
                "--report",
                str(report),
                "--backend",
                "guix",
                *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )


class InstallModeTests(unittest.TestCase):
    def test_install_mode_returns_preview_not_execute(self) -> None:
        result = run_cli(
            "--install",
            "--target-disk",
            "/dev/nvme0n1",
            "--target-size-bytes",
            str(256 * GIB),
            "--acknowledge-disk",
            "/dev/nvme0n1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "preview")
        self.assertTrue(all(step["status"] == "skipped" for step in payload["steps"]))
        self.assertEqual(payload["handoff"][:3], ["guix", "system", "init"])

    def test_install_without_disk_is_refused(self) -> None:
        result = run_cli("--install", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target-disk", result.stderr)

    def test_install_without_size_is_refused(self) -> None:
        result = run_cli("--install", "--target-disk", "/dev/nvme0n1", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target-size-bytes", result.stderr)

    def test_partition_path_is_refused(self) -> None:
        result = run_cli(
            "--install",
            "--target-disk",
            "/dev/nvme0n1p1",
            "--target-size-bytes",
            str(256 * GIB),
            "--acknowledge-disk",
            "/dev/nvme0n1p1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("disk.path", result.stderr)

    def test_execute_is_refused_even_with_matching_acknowledgement(self) -> None:
        """A matching string and caller-supplied size are not authorization."""
        result = run_cli(
            "--install",
            "--execute",
            "--target-disk",
            "/dev/nvme0n1",
            "--target-size-bytes",
            str(256 * GIB),
            "--acknowledge-disk",
            "/dev/nvme0n1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_guided_execute_is_refused_before_interactive_io(self) -> None:
        result = run_cli(
            "--guided",
            "--execute",
            "--target-disk",
            "/dev/nvme0n1",
            "--target-size-bytes",
            str(256 * GIB),
            "--acknowledge-disk",
            "/dev/nvme0n1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_tui_execute_is_refused_before_terminal_access(self) -> None:
        result = run_cli(
            "--tui",
            "--execute",
            "--target-disk",
            "/dev/nvme0n1",
            "--target-size-bytes",
            str(256 * GIB),
            "--acknowledge-disk",
            "/dev/nvme0n1",
            "--quiet",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_write_plan_creates_only_a_preview_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = directory / "report.json"
            report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            output = directory / "plan.json"
            result = subprocess.run(
                [
                    sys.executable, "-m", "wsm_install",
                    "--preflight", "--dry-run", "--report", str(report),
                    "--backend", "guix",
                    "--install", "--target-disk", "/dev/nvme0n1",
                    "--target-size-bytes", str(256 * GIB),
                    "--acknowledge-disk", "/dev/nvme0n1",
                    "--write-plan", str(output), "--quiet",
                ],
                capture_output=True, text=True, check=False, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "wsm-install-plan/1")
            self.assertEqual(payload["disk"], "/dev/nvme0n1")
            self.assertTrue(payload["steps"])
            self.assertIn("APPLY is disabled", result.stderr)

    def test_write_plan_refuses_symlink_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = directory / "report.json"
            report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            protected = directory / "protected.txt"
            protected.write_text("unchanged", encoding="utf-8")
            link = directory / "plan.json"
            link.symlink_to(protected)
            result = subprocess.run(
                [
                    sys.executable, "-m", "wsm_install",
                    "--preflight", "--dry-run", "--report", str(report),
                    "--backend", "guix",
                    "--install", "--target-disk", "/dev/nvme0n1",
                    "--target-size-bytes", str(256 * GIB),
                    "--acknowledge-disk", "/dev/nvme0n1",
                    "--write-plan", str(link), "--quiet",
                ],
                capture_output=True, text=True, check=False, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsafe plan output", result.stderr)
            self.assertEqual(protected.read_text(encoding="utf-8"), "unchanged")


if __name__ == "__main__":
    unittest.main()
