# SPDX-License-Identifier: LicenseRef-Volnist
"""The privileged worker validates untrusted plans and never performs APPLY."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.agent import (  # noqa: E402
    ALLOWED_PROGRAMS,
    MAX_PLAN_BYTES,
    AgentError,
    load_plan,
    run_plan,
    validate_command,
    validate_plan,
)

GOOD = ["/usr/sbin/mkfs.ext4", "-F", "/dev/nvme0n1p2"]


def plan(*commands: list[str], disk: str = "/dev/nvme0n1") -> dict:
    return {
        "schema": "wsm-install-plan/1",
        "disk": disk,
        "steps": [
            {"command": command, "purpose": "test step", "destructive": index == 0}
            for index, command in enumerate(commands)
        ],
    }


class AllowlistTests(unittest.TestCase):
    def test_absolute_allowed_program_passes(self) -> None:
        validate_command(GOOD)

    def test_shell_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_command(["/bin/sh", "-c", "rm -rf /"])
        self.assertEqual(caught.exception.code, "agent.not-allowed")

    def test_unknown_program_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command(["/usr/bin/dd", "if=/dev/zero", "of=/dev/nvme0n1"])

    def test_bare_name_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command(["mkfs.ext4", "-F", "/dev/nvme0n1p2"])

    def test_shell_metacharacter_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_command(["/usr/bin/mount", "/dev/sda1; rm -rf /", "/mnt"])
        self.assertEqual(caught.exception.code, "agent.shell-metacharacter")

    def test_command_substitution_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command(["/usr/bin/mount", "$(reboot)", "/mnt"])

    def test_empty_and_non_string_argv_are_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command([])
        with self.assertRaises(AgentError):
            validate_command(["/usr/bin/mount", 1])  # type: ignore[list-item]

    def test_allowlist_is_absolute(self) -> None:
        self.assertTrue(ALLOWED_PROGRAMS)
        self.assertTrue(all(program.startswith("/") for program in ALLOWED_PROGRAMS))


class PlanTests(unittest.TestCase):
    def test_good_plan_is_accepted(self) -> None:
        steps = validate_plan(plan(GOOD, ["/usr/bin/mount", "/dev/nvme0n1p2", "/mnt"]))
        self.assertEqual(len(steps), 2)
        self.assertTrue(steps[0].destructive)

    def test_wrong_schema_is_refused(self) -> None:
        document = plan(GOOD)
        document["schema"] = "other/1"
        with self.assertRaises(AgentError) as caught:
            validate_plan(document)
        self.assertEqual(caught.exception.code, "agent.bad-schema")

    def test_empty_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan({"schema": "wsm-install-plan/1", "disk": "/dev/nvme0n1", "steps": []})

    def test_too_many_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_plan(plan(*([GOOD] * 40)))
        self.assertEqual(caught.exception.code, "agent.too-many-steps")

    def test_non_object_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan(["not", "an", "object"])

    def test_partition_for_another_disk_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_plan(plan(["/usr/sbin/mkfs.ext4", "-F", "/dev/sda2"]))
        self.assertEqual(caught.exception.code, "agent.target-mismatch")

    def test_partition_device_as_whole_disk_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_plan(plan(GOOD, disk="/dev/nvme0n1p2"))
        self.assertEqual(caught.exception.code, "agent.bad-disk")

    def test_non_boolean_destructive_flag_is_refused(self) -> None:
        document = plan(GOOD)
        document["steps"][0]["destructive"] = "false"
        with self.assertRaises(AgentError):
            validate_plan(document)

    def test_unreadable_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            load_plan(Path("/nonexistent/plan.json"))
        self.assertEqual(caught.exception.code, "agent.unreadable-plan")

    def test_symlink_plan_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            link = root / "plan.json"
            link.symlink_to(target)
            with self.assertRaises(AgentError) as caught:
                load_plan(link)
        self.assertEqual(caught.exception.code, "agent.unsafe-plan-path")

    def test_oversized_plan_is_refused_before_json_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_bytes(b" " * (MAX_PLAN_BYTES + 1))
            with self.assertRaises(AgentError) as caught:
                load_plan(path)
        self.assertEqual(caught.exception.code, "agent.plan-too-large")


class ExecutionTests(unittest.TestCase):
    def test_preview_calls_only_the_shared_preview_executor(self) -> None:
        document = plan(GOOD)
        steps = validate_plan(document)
        with patch("wsm_install.agent.execute", return_value=[]) as execute_mock:
            self.assertEqual(run_plan(document, steps, dry_run=True), 0)
        execute_mock.assert_called_once_with(steps, disk=document["disk"], dry_run=True)

    def test_non_dry_run_is_refused_before_executor(self) -> None:
        document = plan(GOOD)
        steps = validate_plan(document)
        with patch("wsm_install.agent.execute") as execute_mock:
            with self.assertRaises(AgentError) as caught:
                run_plan(document, steps, dry_run=False)
        self.assertEqual(caught.exception.code, "agent.apply-disabled")
        execute_mock.assert_not_called()

    def test_unvalidated_steps_are_refused(self) -> None:
        document = plan(GOOD)
        with self.assertRaises(AgentError) as caught:
            run_plan(document, [], dry_run=True)
        self.assertEqual(caught.exception.code, "agent.plan-mismatch")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "wsm_install.agent", *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )

    def test_plan_is_preview_only_even_without_dry_run_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preview accepted", result.stdout)
        self.assertIn("no disk was changed", result.stdout)

    def test_legacy_dry_run_flag_is_still_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_execute_flag_is_not_a_supported_option(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path), "--execute")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
