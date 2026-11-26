# SPDX-License-Identifier: LicenseRef-Volnist
"""The privileged worker is a narrow door: these tests are the door frame."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.agent import (  # noqa: E402
    ALLOWED_PROGRAMS,
    AgentError,
    load_plan,
    run_plan,
    validate_command,
    validate_plan,
)


def plan(*commands: list[str], disk: str = "/dev/nvme0n1") -> dict:
    return {
        "schema": "wsm-install-plan/1",
        "disk": disk,
        "steps": [
            {"command": command, "purpose": "test", "destructive": index == 0}
            for index, command in enumerate(commands)
        ],
    }


GOOD = ["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"]


class AllowlistTests(unittest.TestCase):
    def test_allowed_program_passes(self) -> None:
        validate_command(GOOD)

    def test_shell_is_refused(self) -> None:
        """A compromised UI must not be able to run a shell through the agent."""
        with self.assertRaises(AgentError) as caught:
            validate_command(["/bin/sh", "-c", "rm -rf /"])
        self.assertEqual(caught.exception.code, "agent.not-allowed")

    def test_unknown_program_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command(["/usr/bin/dd", "if=/dev/zero", "of=/dev/nvme0n1"])

    def test_bare_name_is_refused(self) -> None:
        """PATH lookup in a root context is the Omarchy #8172 mistake."""
        with self.assertRaises(AgentError):
            validate_command(["mkfs.ext4", "-F", "/dev/nvme0n1p2"])

    def test_shell_metacharacter_in_argument_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_command(["/usr/bin/mount", "/dev/sda1; rm -rf /", "/mnt"])
        self.assertEqual(caught.exception.code, "agent.shell-metacharacter")

    def test_command_substitution_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command(["/usr/bin/mount", "$(reboot)", "/mnt"])

    def test_empty_command_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command([])


class PlanTests(unittest.TestCase):
    def test_good_plan_is_accepted(self) -> None:
        steps = validate_plan(plan(GOOD, ["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"]))
        self.assertEqual(len(steps), 2)
        self.assertTrue(steps[0].destructive)

    def test_wrong_schema_is_refused(self) -> None:
        document = plan(GOOD)
        document["schema"] = "something-else/1"
        with self.assertRaises(AgentError) as caught:
            validate_plan(document)
        self.assertEqual(caught.exception.code, "agent.bad-schema")

    def test_empty_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan({"schema": "wsm-install-plan/1", "disk": "/dev/x", "steps": []})

    def test_too_many_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_plan(plan(*([GOOD] * 40)))
        self.assertEqual(caught.exception.code, "agent.too-many-steps")

    def test_non_object_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan(["not", "a", "plan"])

    def test_unreadable_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            load_plan(Path("/nonexistent/plan.json"))
        self.assertEqual(caught.exception.code, "agent.unreadable-plan")


class ExecutionTests(unittest.TestCase):
    def test_dry_run_validates_and_previews_without_execution_api(self) -> None:
        document = plan(GOOD)
        steps = validate_plan(document)
        code = run_plan(document, steps, dry_run=True)
        self.assertEqual(code, 0)

    def test_real_run_is_refused_before_any_runner_can_be_injected(self) -> None:
        document = plan(GOOD)
        steps = validate_plan(document)
        with self.assertRaises(AgentError) as caught:
            run_plan(document, steps, dry_run=False)
        self.assertEqual(caught.exception.code, "agent.apply-disabled")

    def test_plan_without_a_whole_disk_is_refused(self) -> None:
        document = plan(GOOD)
        document["disk"] = "/dev/nvme0n1p1"
        with self.assertRaises(AgentError) as caught:
            run_plan(document, validate_plan(document), dry_run=True)
        self.assertEqual(caught.exception.code, "agent.bad-disk")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "wsm_install.agent", *args],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )

    def test_dry_run_accepts_a_valid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("previewed; APPLY disabled", result.stdout)

    def test_plan_with_shell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(["/bin/sh", "-c", "true"])), encoding="utf-8")
            result = self.run_cli("--plan", str(path), "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("agent.not-allowed", result.stderr)

    def test_recover_requires_a_journal_path(self) -> None:
        result = self.run_cli("--recover")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--plan is required with --recover", result.stderr)

    def test_apply_without_dry_run_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("agent.apply-disabled", result.stderr)
        self.assertNotIn("executed", result.stdout)

    def test_allowlist_is_not_empty_and_all_absolute(self) -> None:
        self.assertTrue(ALLOWED_PROGRAMS)
        for program in ALLOWED_PROGRAMS:
            self.assertTrue(program.startswith("/"), program)


if __name__ == "__main__":
    unittest.main()
