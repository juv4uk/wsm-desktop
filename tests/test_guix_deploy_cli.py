# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the plan-only Guix deployment handoff CLI."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.backend_guix import TargetSelection  # noqa: E402
from wsm_install.guix_deploy import (
    DeployCliError,
    _ensure_output_not_on_target_filesystem,
    _ensure_output_outside_target,
    main,
)  # noqa: E402
from wsm_install.plan import build_plan, canonical_json  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


def confirmed_plan() -> dict:
    report_bytes = FIXTURE.read_bytes()
    report = json.loads(report_bytes)
    plan, _, _ = build_plan(report, report_bytes, "guix")
    plan = copy.deepcopy(plan)
    plan["blockers"] = []
    plan["plan_readiness"]["confirmable"] = True
    plan["plan_readiness"]["missing_required_roles"] = []
    plan["plan_readiness"]["required_user_actions"] = []
    plan["plan_status"] = "confirmation-ready"
    plan["execution"]["plan_confirmable"] = True
    plan["execution"]["mutations_authorized"] = False
    plan["execution"]["backend_invoked"] = False
    plan["execution"]["disk_access_performed"] = False
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return plan


def target_selection() -> TargetSelection:
    return TargetSelection(
        disk="/dev/vda",
        hostname="wsm",
        timezone="Europe/Kyiv",
        locale="en_US.utf8",
        keyboard_layout="us",
        username="wsmuser",
        full_name="WSM User",
        root_label="wsm-root",
        efi_label="wsm-efi",
        boot_mode="efi",
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class GuixDeployCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan_path = self.root / "plan.json"
        self.selection_path = self.root / "selection.json"
        self.output_path = self.root / "system.scm"
        self.plan = confirmed_plan()
        self.selection = target_selection()
        write_json(self.plan_path, self.plan)
        write_json(self.selection_path, self.selection.__dict__)

    def run_cli(self, *extra: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            "--plan", str(self.plan_path),
            "--selection", str(self.selection_path),
            *extra,
        ]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_show_confirmation_prints_digests_without_creating_config(self) -> None:
        code, stdout, stderr = self.run_cli("--show-confirmation")
        payload = json.loads(stdout)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "confirmation-required")
        self.assertEqual(payload["plan_sha256"], self.plan["plan_sha256"])
        self.assertEqual(payload["target_digest"], self.selection.digest())
        self.assertFalse(payload["configuration_created"])
        self.assertFalse(payload["deployment_executed"])
        self.assertFalse(self.output_path.exists())

    def test_confirmed_handoff_writes_private_scheme_file_and_prints_argv(self) -> None:
        code, stdout, stderr = self.run_cli(
            "--output", str(self.output_path),
            "--confirm-plan-sha256", self.plan["plan_sha256"],
            "--confirm-target-digest", self.selection.digest(),
        )
        payload = json.loads(stdout)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "prepared-not-executed")
        self.assertEqual(
            payload["argv"],
            ["guix", "system", "init", "/run/wsm/system.scm", "/mnt"],
        )
        self.assertEqual(payload["configuration_path"], str(self.output_path))
        self.assertFalse(payload["deployment_executed"])
        self.assertFalse(payload["target_disk_mutated"])
        self.assertTrue(self.output_path.is_file())
        self.assertIn("(operating-system", self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(self.output_path.stat().st_mode & 0o777, 0o600)

    def test_plan_confirmation_mismatch_refuses_before_creating_output(self) -> None:
        code, _stdout, stderr = self.run_cli(
            "--output", str(self.output_path),
            "--confirm-plan-sha256", "0" * 64,
            "--confirm-target-digest", self.selection.digest(),
        )
        self.assertEqual(code, 3)
        self.assertIn("confirmation.plan_sha256", stderr)
        self.assertFalse(self.output_path.exists())

    def test_target_confirmation_mismatch_refuses_before_creating_output(self) -> None:
        code, _stdout, stderr = self.run_cli(
            "--output", str(self.output_path),
            "--confirm-plan-sha256", self.plan["plan_sha256"],
            "--confirm-target-digest", "0" * 64,
        )
        self.assertEqual(code, 3)
        self.assertIn("confirmation.target_digest", stderr)
        self.assertFalse(self.output_path.exists())

    def test_malformed_nested_plan_fields_are_refused(self) -> None:
        malformed = copy.deepcopy(self.plan)
        malformed["backend"] = "guix-system"
        malformed.pop("plan_sha256", None)
        malformed["plan_sha256"] = hashlib.sha256(
            canonical_json(malformed).encode("utf-8")
        ).hexdigest()
        write_json(self.plan_path, malformed)
        code, _stdout, stderr = self.run_cli("--show-confirmation")
        self.assertEqual(code, 2)
        self.assertIn("plan field 'backend' must be a JSON object", stderr)
        self.assertFalse(self.output_path.exists())

    def test_diagnostic_status_is_refused_even_with_confirmable_flag(self) -> None:
        diagnostic = copy.deepcopy(self.plan)
        diagnostic["plan_status"] = "diagnostic-only"
        diagnostic.pop("plan_sha256", None)
        diagnostic["plan_sha256"] = hashlib.sha256(
            canonical_json(diagnostic).encode("utf-8")
        ).hexdigest()
        write_json(self.plan_path, diagnostic)
        code, _stdout, stderr = self.run_cli("--show-confirmation")
        self.assertEqual(code, 3)
        self.assertIn("plan.not_confirmation_ready", stderr)
        self.assertFalse(self.output_path.exists())

    def test_execution_confirmation_mismatch_is_refused(self) -> None:
        invalid = copy.deepcopy(self.plan)
        invalid["execution"]["plan_confirmable"] = False
        invalid.pop("plan_sha256", None)
        invalid["plan_sha256"] = hashlib.sha256(
            canonical_json(invalid).encode("utf-8")
        ).hexdigest()
        write_json(self.plan_path, invalid)
        code, _stdout, stderr = self.run_cli("--show-confirmation")
        self.assertEqual(code, 3)
        self.assertIn("plan.execution_not_confirmable", stderr)
        self.assertFalse(self.output_path.exists())

    def test_diagnostic_only_plan_is_refused_before_creating_output(self) -> None:
        diagnostic = copy.deepcopy(self.plan)
        diagnostic["plan_readiness"]["confirmable"] = False
        diagnostic.pop("plan_sha256", None)
        diagnostic["plan_sha256"] = hashlib.sha256(
            canonical_json(diagnostic).encode("utf-8")
        ).hexdigest()
        write_json(self.plan_path, diagnostic)
        code, _stdout, stderr = self.run_cli(
            "--output", str(self.output_path),
            "--confirm-plan-sha256", diagnostic["plan_sha256"],
            "--confirm-target-digest", self.selection.digest(),
        )
        self.assertEqual(code, 3)
        self.assertIn("plan.not_confirmable", stderr)
        self.assertFalse(self.output_path.exists())

    def test_existing_output_is_never_overwritten(self) -> None:
        sentinel = "do not replace"
        self.output_path.write_text(sentinel, encoding="utf-8")
        code, _stdout, stderr = self.run_cli(
            "--output", str(self.output_path),
            "--confirm-plan-sha256", self.plan["plan_sha256"],
            "--confirm-target-digest", self.selection.digest(),
        )
        self.assertEqual(code, 2)
        self.assertIn("refusing to overwrite", stderr)
        self.assertEqual(self.output_path.read_text(encoding="utf-8"), sentinel)

    def test_output_must_be_an_absolute_scm_path(self) -> None:
        code, _stdout, stderr = self.run_cli(
            "--output", "relative/system.scm",
            "--confirm-plan-sha256", self.plan["plan_sha256"],
            "--confirm-target-digest", self.selection.digest(),
        )
        self.assertEqual(code, 2)
        self.assertIn("must be absolute", stderr)
        self.assertFalse(self.output_path.exists())

    def test_output_may_not_alias_plan_input(self) -> None:
        scm_plan = self.root / "input.scm"
        write_json(scm_plan, self.plan)
        # The suffix is valid, but the same path is also supplied as --plan.
        arguments = [
            "--plan", str(scm_plan),
            "--selection", str(self.selection_path),
            "--output", str(scm_plan),
            "--confirm-plan-sha256", self.plan["plan_sha256"],
            "--confirm-target-digest", self.selection.digest(),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        self.assertEqual(code, 2)
        self.assertIn("must not overwrite an input", stderr.getvalue())
        self.assertEqual(json.loads(scm_plan.read_text(encoding="utf-8")), self.plan)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        self.plan_path.write_text('{"plan_sha256":"a","plan_sha256":"b"}', encoding="utf-8")
        code, _stdout, stderr = self.run_cli("--show-confirmation")
        self.assertEqual(code, 2)
        self.assertIn("duplicate JSON object key", stderr)
        self.assertFalse(self.output_path.exists())

    def test_selection_with_unknown_fields_is_rejected(self) -> None:
        invalid = dict(self.selection.__dict__)
        invalid["partition_guess"] = "/dev/vda1"
        write_json(self.selection_path, invalid)
        code, _stdout, stderr = self.run_cli("--show-confirmation")
        self.assertEqual(code, 2)
        self.assertIn("extra=['partition_guess']", stderr)

    def test_symlink_input_is_refused(self) -> None:
        link = self.root / "plan-link.json"
        try:
            link.symlink_to(self.plan_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        arguments = [
            "--plan", str(link),
            "--selection", str(self.selection_path),
            "--show-confirmation",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        self.assertEqual(code, 2)
        self.assertIn("cannot open plan", stderr.getvalue())

    def test_review_output_may_not_live_inside_the_target_mountpoint(self) -> None:
        for candidate in (Path("/mnt"), Path("/mnt/system.scm"), Path("/mnt/wsm/review.scm")):
            with self.subTest(candidate=str(candidate)):
                with self.assertRaises(DeployCliError) as raised:
                    _ensure_output_outside_target(candidate)
                self.assertIn("outside the target mountpoint", str(raised.exception))

    def test_review_output_is_refused_on_same_filesystem_bind_mount_even_if_ismount_is_false(self) -> None:
        # Python's ismount may return False for a same-filesystem bind mount.
        # mountinfo still contains the exact /mnt mountpoint, so st_dev must be compared.
        mountinfo = "36 25 8:1 / /mnt rw,relatime - ext4 /dev/vda1 rw\n"
        fake_stat = type("StatResult", (), {"st_dev": 123})()
        with (
            patch.object(Path, "read_text", return_value=mountinfo),
            patch.object(Path, "stat", return_value=fake_stat),
            patch("wsm_install.guix_deploy.os.path.ismount", return_value=False),
        ):
            with self.assertRaises(DeployCliError) as raised:
                _ensure_output_not_on_target_filesystem(self.root / "review.scm")
        self.assertIn("share the mounted target filesystem", str(raised.exception))

    def test_review_output_on_separate_filesystem_is_allowed(self) -> None:
        mountinfo = "36 25 8:1 / /mnt rw,relatime - ext4 /dev/vda1 rw\n"
        target_stat = type("StatResult", (), {"st_dev": 123})()
        output_stat = type("StatResult", (), {"st_dev": 456})()

        def fake_stat(path: Path):
            return target_stat if path == Path("/mnt") else output_stat

        with (
            patch.object(Path, "read_text", return_value=mountinfo),
            patch.object(Path, "stat", autospec=True, side_effect=fake_stat),
        ):
            _ensure_output_not_on_target_filesystem(self.root / "review.scm")

    def test_review_output_skips_device_comparison_when_mountinfo_has_no_target_mount(self) -> None:
        root_mount = "1 0 8:1 / / rw,relatime - ext4 /dev/root rw\n"
        with (
            patch.object(Path, "read_text", return_value=root_mount),
            patch.object(Path, "stat", side_effect=AssertionError("stat must not be called")),
        ):
            _ensure_output_not_on_target_filesystem(self.root / "review.scm")

    def test_review_output_fails_closed_when_mountinfo_is_unavailable(self) -> None:
        with patch.object(Path, "read_text", side_effect=OSError("proc unavailable")):
            with self.assertRaisesRegex(DeployCliError, "cannot read target mount table"):
                _ensure_output_not_on_target_filesystem(self.root / "review.scm")

    def test_review_output_fails_closed_on_malformed_mountinfo_after_target_entry(self) -> None:
        malformed = "36 25 8:1 / /mnt rw,relatime - ext4 /dev/vda1 rw\nmalformed\n"
        with patch.object(Path, "read_text", return_value=malformed):
            with self.assertRaisesRegex(DeployCliError, "mountinfo line 2 is malformed"):
                _ensure_output_not_on_target_filesystem(self.root / "review.scm")

    def test_review_output_fails_closed_on_malformed_mountinfo(self) -> None:
        malformed = "36 25 8:1 / /mnt rw,relatime\n"
        with patch.object(Path, "read_text", return_value=malformed):
            with self.assertRaisesRegex(DeployCliError, "mountinfo line 1 is malformed"):
                _ensure_output_not_on_target_filesystem(self.root / "review.scm")

    def test_mountinfo_path_escape_is_decoded(self) -> None:
        from wsm_install.guix_deploy import _decode_mountinfo_field

        self.assertEqual(_decode_mountinfo_field(r"/target\040drive\134name"), "/target drive\\name")
        with self.assertRaisesRegex(DeployCliError, "invalid octal path escape"):
            _decode_mountinfo_field(r"/target\04x")

    def test_custom_mountpoint_is_not_a_cli_option(self) -> None:
        # The backend allow-list fixes the installer-owned mount root; a CLI
        # option would only invite callers to request an argv we must refuse.
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(
                "--output", str(self.output_path),
                "--mountpoint", "relative",
                "--confirm-plan-sha256", self.plan["plan_sha256"],
                "--confirm-target-digest", self.selection.digest(),
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(self.output_path.exists())


if __name__ == "__main__":
    unittest.main()