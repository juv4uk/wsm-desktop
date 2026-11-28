# SPDX-License-Identifier: LicenseRef-Volnist
"""The privileged worker is a narrow door: these tests are the door frame."""

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


def profile_path(name: str) -> str:
    return f"/run/current-system/profile/bin/{name}"


GOOD = [profile_path("mkfs.ext4"), "-F", "/dev/nvme0n1p2"]


def validate_command_with_profile(command):
    directory = Path(command[0]).parent.name
    resolver = lambda name: f"/run/current-system/profile/{directory}/{name}"
    with patch("wsm_install.agent.resolve_trusted_tool", side_effect=resolver):
        return validate_command(command)


def validate_plan_with_profile(document):
    with patch("wsm_install.agent.resolve_trusted_tool", side_effect=profile_path):
        return validate_plan(document)


class AllowlistTests(unittest.TestCase):
    def test_allowed_program_passes(self) -> None:
        validate_command_with_profile(GOOD)

    def test_agent_accepts_all_exact_profile_paths_including_sgdisk(self) -> None:
        expected = {
            f"/run/current-system/profile/{directory}/{name}"
            for directory in ("bin", "sbin")
            for name in ("sgdisk", "partprobe", "udevadm", "mkfs.ext4", "mkfs.fat", "mount", "mkdir")
        }
        self.assertEqual(ALLOWED_PROGRAMS, expected)
        for directory in ("bin", "sbin"):
            for name in ("sgdisk", "partprobe", "udevadm", "mkfs.ext4", "mkfs.fat", "mount", "mkdir"):
                program = f"/run/current-system/profile/{directory}/{name}"
                with self.subTest(program=program):
                    validate_command_with_profile([program, "--version"])

    def test_shell_and_unknown_programs_are_refused(self) -> None:
        for program in ("/bin/sh", "/run/current-system/profile/bin/dd"):
            with self.subTest(program=program), self.assertRaises(AgentError) as caught:
                validate_command_with_profile([program, "-c", "true"])
            self.assertEqual(caught.exception.code, "agent.not-allowed")

    def test_legacy_fhs_bare_and_arbitrary_paths_are_refused(self) -> None:
        for program in (
            "/usr/sbin/mkfs.ext4",
            "/usr/bin/mount",
            "mkfs.ext4",
            "/tmp/mkfs.ext4",
            "/run/current-system/profile/../../tmp/mkfs.ext4",
        ):
            with self.subTest(program=program), self.assertRaises(AgentError) as caught:
                validate_command_with_profile([program, "-F", "/dev/nvme0n1p2"])
            self.assertEqual(caught.exception.code, "agent.not-allowed")

    def test_btrfs_and_xfs_formatters_are_not_allowed_for_ext4_guix_target(self) -> None:
        for formatter in (
            profile_path("mkfs.btrfs"),
            profile_path("mkfs.xfs"),
        ):
            with self.subTest(formatter=formatter), self.assertRaises(AgentError) as caught:
                validate_command_with_profile([formatter, "-f", "/dev/nvme0n1p2"])
            self.assertEqual(caught.exception.code, "agent.not-allowed")

    def test_missing_profile_executable_fails_closed(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_command([profile_path("mkfs.ext4"), "-F", "/dev/nvme0n1p2"])
        self.assertEqual(caught.exception.code, "agent.tool-unavailable")

    def test_shell_metacharacter_in_argument_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_command_with_profile(
                [profile_path("mount"), "/dev/sda1; rm -rf /", "/mnt"]
            )
        self.assertEqual(caught.exception.code, "agent.shell-metacharacter")

    def test_command_substitution_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command_with_profile([profile_path("mount"), "$(reboot)", "/mnt"])

    def test_empty_command_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_command([])


class PlanTests(unittest.TestCase):
    def test_good_plan_is_accepted(self) -> None:
        steps = validate_plan_with_profile(
            plan(GOOD, [profile_path("mount"), "/dev/nvme0n1p2", "/mnt"])
        )
        self.assertEqual(len(steps), 2)
        self.assertTrue(steps[0].destructive)

    def test_wrong_schema_is_refused(self) -> None:
        document = plan(GOOD)
        document["schema"] = "something-else/1"
        with self.assertRaises(AgentError) as caught:
            validate_plan_with_profile(document)
        self.assertEqual(caught.exception.code, "agent.bad-schema")

    def test_empty_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan_with_profile(
                {"schema": "wsm-install-plan/1", "disk": "/dev/x", "steps": []}
            )

    def test_too_many_steps_are_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            validate_plan_with_profile(plan(*([GOOD] * 40)))
        self.assertEqual(caught.exception.code, "agent.too-many-steps")

    def test_non_object_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError):
            validate_plan_with_profile(["not", "a", "plan"])

    def test_unreadable_plan_is_refused(self) -> None:
        with self.assertRaises(AgentError) as caught:
            load_plan(Path("/nonexistent/plan.json"))
        self.assertEqual(caught.exception.code, "agent.unreadable-plan")


class ExecutionTests(unittest.TestCase):
    def test_dry_run_validates_and_previews_without_execution_api(self) -> None:
        document = plan(GOOD)
        steps = validate_plan_with_profile(document)
        code = run_plan(document, steps, dry_run=True)
        self.assertEqual(code, 0)

    def test_real_run_is_refused_before_any_runner_can_be_injected(self) -> None:
        document = plan(GOOD)
        steps = validate_plan_with_profile(document)
        with self.assertRaises(AgentError) as caught:
            run_plan(document, steps, dry_run=False)
        self.assertEqual(caught.exception.code, "agent.apply-disabled")

    def test_plan_without_a_whole_disk_is_refused(self) -> None:
        document = plan(GOOD)
        document["disk"] = "/dev/nvme0n1p1"
        with self.assertRaises(AgentError) as caught:
            run_plan(document, validate_plan_with_profile(document), dry_run=True)
        self.assertEqual(caught.exception.code, "agent.bad-disk")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        runner = r"""
import sys
from unittest.mock import patch
import wsm_install.agent as agent

def profile_path(name):
    return f"/run/current-system/profile/bin/{name}"

with patch.object(agent, "resolve_trusted_tool", side_effect=profile_path):
    raise SystemExit(agent.main(sys.argv[1:]))
"""
        return subprocess.run(
            [sys.executable, "-c", runner, *args],
            capture_output=True, text=True, check=False, cwd=ROOT,
        )

    def test_dry_run_accepts_a_valid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan(GOOD)), encoding="utf-8")
            result = self.run_cli("--plan", str(path), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("previewed 1 step(s); APPLY disabled", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
