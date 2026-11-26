# SPDX-License-Identifier: LicenseRef-Volnist
"""Regression tests for the single-workflow WSM acceptance contract."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class CiAcceptancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.load(
            WORKFLOW.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        cls.jobs = cls.workflow["jobs"]

    def test_required_workflow_events_are_not_path_filtered(self) -> None:
        events = self.workflow["on"]
        self.assertIn("push", events)
        self.assertIn("pull_request", events)
        self.assertIn("workflow_dispatch", events)
        self.assertNotIn("paths", events.get("push") or {})
        self.assertNotIn("paths", events.get("pull_request") or {})

    def test_push_ci_runs_only_on_main_without_path_filters(self) -> None:
        push = self.workflow["on"]["push"]
        self.assertEqual(push["branches"], ["main"])
        self.assertNotIn("paths", push)

    def test_qemu_acceptance_is_unconditional_and_bounded(self) -> None:
        job = self.jobs["qemu-acceptance"]
        self.assertNotIn("if", job)
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        timeout = int(job["timeout-minutes"])
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 30)

    def test_qemu_job_runs_all_guest_acceptance_layers(self) -> None:
        steps = self.jobs["qemu-acceptance"]["steps"]
        commands = "\n".join(step.get("run", "") for step in steps)
        for marker in (
            "scripts/ci_qemu_guest_smoke.sh",
            "scripts/ci_qemu_hwcheck_guest.py",
            "scripts/ci_cxl_qemu_guest.py",
            "scripts/qemu_boot_smoke.py",
            "WSM_QEMU_HARNESS_ISO_BOOT_OK",
            "test_install_capability_matrix.py",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, commands)

    def test_fast_channel_gate_checks_free_and_compatibility_locks_separately(self) -> None:
        checks = self.jobs["checks"]["steps"]
        command = "\n".join(step.get("run", "") for step in checks)
        self.assertIn("--lock channels.lock.scm --policy free", command)
        self.assertIn("--lock channels/compatibility.lock.scm --policy compatibility", command)

    def test_qemu_job_installs_every_required_tool(self) -> None:
        commands = "\n".join(
            step.get("run", "") for step in self.jobs["qemu-acceptance"]["steps"]
        )
        for package in (
            "qemu-system-x86",
            "qemu-utils",
            "busybox-static",
            "cpio",
            "zstd",
            "xz-utils",
            "kmod",
            "grub-pc-bin",
            "xorriso",
            "mtools",
        ):
            with self.subTest(package=package):
                self.assertIn(package, commands)

    def test_manual_guix_gate_does_not_hide_missing_compatibility_lock(self) -> None:
        guix = self.jobs["guix"]
        commands = "\n".join(step.get("run", "") for step in guix["steps"])
        self.assertIn("workflow_dispatch", guix["if"])
        self.assertIn("NOT_CONFIGURED", commands)
        self.assertIn("channels/compatibility.lock.scm", commands)
        self.assertIn("systems/compatibility.scm", commands)
        self.assertIn("systems/live-compat.scm", commands)
        self.assertIn("exit 2", commands)

    def test_aggregate_gate_requires_fast_qemu_and_manual_results(self) -> None:
        aggregate = self.jobs["acceptance-gates"]
        self.assertEqual(aggregate["if"], "always()")
        self.assertEqual(
            set(aggregate["needs"]),
            {"checks", "qemu-acceptance", "guix"},
        )
        commands = "\n".join(
            step.get("run", "") for step in aggregate["steps"]
        )
        for status in (
            "CHECKS_RESULT",
            "QEMU_RESULT",
            "GUIX_RESULT",
            "workflow_dispatch",
            "not-run",
        ):
            with self.subTest(status=status):
                self.assertIn(status, commands)

    def test_workflow_has_one_aggregate_gate_and_read_only_permissions(self) -> None:
        self.assertEqual(self.workflow["permissions"]["contents"], "read")
        self.assertEqual(
            [name for name in self.jobs if name == "acceptance-gates"],
            ["acceptance-gates"],
        )
        self.assertNotIn("secrets.", WORKFLOW.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
