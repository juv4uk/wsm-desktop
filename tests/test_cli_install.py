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
sys.path.insert(0, str(ROOT))  # Make direct test-file execution resolve the project package.
GIB = 1024 ** 3

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "complete-machine.json"
PARTIAL = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


def run_cli(*extra: str, backend: str = "guix") -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "report.json"
        report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "wsm_install", "--preflight", "--dry-run",
             "--report", str(report), "--backend", backend, *extra],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )


class InstallModeTests(unittest.TestCase):
    def test_deferred_backends_are_rejected_by_cli(self) -> None:
        for backend in ("nix", "nixos"):
            with self.subTest(backend=backend):
                result = run_cli(backend=backend)
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid choice", result.stderr)
                self.assertNotIn("plan_sha256", result.stdout)

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
        commands = [step["command"] for step in payload["steps"]]
        names = [Path(command[0]).name for command in commands]
        self.assertEqual(names[:3], ["sgdisk", "sgdisk", "sgdisk"])
        self.assertEqual(names[3:5], ["partprobe", "udevadm"])
        self.assertTrue(all(step["destructive"] for step in payload["steps"][:3]))
        self.assertEqual(commands[0][1:], ["--zap-all", "/dev/nvme0n1"])
        self.assertEqual(payload["handoff"][:3], ["guix", "system", "init"])

    def test_btrfs_and_xfs_are_refused_by_first_guix_preview(self) -> None:
        for filesystem in ("btrfs", "xfs"):
            with self.subTest(filesystem=filesystem):
                result = run_cli("--filesystem", filesystem)
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid choice", result.stderr)

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

    def test_guided_preview_callback_takes_the_arguments_frontends_pass(self) -> None:
        """The guided/TUI callback must accept (disk, size, firmware) and build a plan.

        It used to call _run_install() with a single Namespace while that function
        takes (args, report, report_bytes), so every interactive run raised
        TypeError. The frontend tests inject their own callback, so nothing caught
        it - this test calls the real one.
        """
        import argparse
        import inspect

        from wsm_install import cli

        args = argparse.Namespace(
            filesystem="ext4",
            mount_point="/mnt",
            system_file=Path("system.scm"),
            backend="guix",
        )
        report = json.loads(FIXTURE.read_text(encoding="utf-8"))
        preview = cli._installer_preview(args, report, FIXTURE.read_bytes())
        self.assertEqual(len(inspect.signature(preview).parameters), 3)

        with tempfile.NamedTemporaryFile() as disk:
            result = preview(disk.name, 16 * GIB, "uefi")
        self.assertIsInstance(result, int)

    def test_guided_execute_is_rejected_before_interaction(self) -> None:
        result = run_cli("--guided", "--execute", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)

    def test_tui_execute_is_rejected_before_interaction(self) -> None:
        result = run_cli("--tui", "--execute", "--quiet")
        self.assertEqual(result.returncode, 2)
        self.assertIn("execute.apply-disabled", result.stderr)


class ClassificationSummaryTests(unittest.TestCase):
    """The three-level view is diagnostic; install gates use report-plan evidence."""

    def build(self, *extra: str, report: Path | None = None) -> subprocess.CompletedProcess:
        return run_cli(
            "--report", str(report or PARTIAL),
            "--install",
            "--target-disk", "/dev/nvme0n1",
            "--target-size-bytes", str(256 * GIB),
            "--acknowledge-disk", "/dev/nvme0n1",
            *extra,
        )

    def test_classify_flag_prints_a_diagnostic_summary(self) -> None:
        result = run_cli("--classify")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "wsm-hardware-classification/2")
        self.assertNotIn("decision", payload)
        self.assertEqual(payload["counts"]["certified"], 0)
        self.assertTrue(all(item["coverage"] == "unknown" for item in payload["subsystems"]))

    def test_absent_storage_record_is_not_a_global_install_stop(self) -> None:
        """The partial report has no storage record; that is not not-detected."""
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("classification.stop", result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertTrue(all(step["status"] == "not-run" for step in payload["steps"]))

    def test_report_declared_unknown_critical_role_blocks_preview_plan(self) -> None:
        """The plan gate consumes a report-declared critical role, not a subsystem label."""
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        value["devices"][0]["criticality"] = ["boot-path"]
        value["devices"][0]["discovery_status"] = "unknown"
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            report.write_text(json.dumps(value), encoding="utf-8")
            result = self.build(report=report)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("plan.blocked", result.stderr)
        self.assertIn("required critical device discovery is unknown", result.stderr)

    def test_read_only_classification_does_not_accept_profile_evidence(self) -> None:
        result = run_cli("--classify", "--profile-evidence", str(ROOT / "missing-evidence.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--profile-evidence is accepted only", result.stderr)


if __name__ == "__main__":
    unittest.main()
