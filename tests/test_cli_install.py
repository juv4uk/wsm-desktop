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

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "complete-machine.json"
PARTIAL = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


_CLI_RUNNER = r"""
import runpy
import sys
from pathlib import Path
import wsm_install.install_steps as install_steps

profile_root = Path(sys.argv[1])
original_plan_steps = install_steps.plan_steps

def _plan_steps_with_profile(*args, **kwargs):
    kwargs.setdefault("profile_root", profile_root)
    return original_plan_steps(*args, **kwargs)

install_steps.plan_steps = _plan_steps_with_profile
sys.argv = ["wsm-install", *sys.argv[2:]]
runpy.run_module("wsm_install", run_name="__main__")
"""


def _create_guix_profile(profile_root: Path) -> None:
    """Build a disposable system-profile fixture for the real CLI entrypoint."""
    from wsm_install.install_steps import TRUSTED_TOOLS

    for index, binary in enumerate(TRUSTED_TOOLS.values()):
        directory = "bin" if index % 2 == 0 else "sbin"
        executable = profile_root / directory / binary
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)


def _run_cli_with_profile(
    report: Path,
    profile_root: Path,
    *extra: str,
    backend: str = "guix",
) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "-c",
        _CLI_RUNNER,
        str(profile_root),
        "--preflight",
        "--dry-run",
        "--report",
        str(report),
        "--backend",
        backend,
        *extra,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def run_cli(*extra: str, backend: str = "guix") -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        report = root / "report.json"
        report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        profile_root = root / "profile"
        _create_guix_profile(profile_root)
        return _run_cli_with_profile(report, profile_root, *extra, backend=backend)


def run_cli_with_report(
    report: Path,
    *extra: str,
    backend: str = "guix",
) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temporary:
        profile_root = Path(temporary) / "profile"
        _create_guix_profile(profile_root)
        return _run_cli_with_profile(report, profile_root, *extra, backend=backend)

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

    def test_install_refuses_cleanly_when_guix_profile_tools_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report.json"
            report.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            empty_profile = root / "empty-profile"
            empty_profile.mkdir()
            result = _run_cli_with_profile(
                report,
                empty_profile,
                "--install", "--target-disk", "/dev/nvme0n1",
                "--target-size-bytes", str(256 * GIB),
                "--acknowledge-disk", "/dev/nvme0n1", "--quiet",
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("install.tool-unavailable", result.stderr)
        self.assertIn("tool.missing", result.stderr)
        self.assertIn("no executable", result.stderr)

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
            result = run_cli_with_report(
                report,
                "--install", "--target-disk", "/dev/nvme0n1",
                "--target-size-bytes", str(256 * GIB),
                "--acknowledge-disk", "/dev/nvme0n1",
                "--write-plan", str(report), "--quiet",
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
