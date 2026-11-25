# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI acceptance tests for the review-only Guix handoff."""

from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.backend_guix import TargetSelection
from wsm_install.guix_handoff import main
from wsm_install.plan import build_plan, canonical_json

FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


def make_selection() -> TargetSelection:
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


def make_plan(*, confirmable: bool) -> dict:
    raw = FIXTURE.read_bytes()
    report = json.loads(raw)
    plan, _, _ = build_plan(report, raw, "guix")
    plan = copy.deepcopy(plan)
    plan["blockers"] = []
    plan["plan_readiness"]["confirmable"] = confirmable
    plan["plan_readiness"]["missing_required_roles"] = []
    plan["plan_readiness"]["required_user_actions"] = []
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = hashlib.sha256(
        canonical_json(plan).encode("utf-8")
    ).hexdigest()
    return plan


class GuixHandoffCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.target = self.root / "target"
        self.output_dir = self.root / "review"
        self.target.mkdir()
        self.output_dir.mkdir()
        self.target_sentinel = self.target / "do-not-change.txt"
        self.target_sentinel.write_text("target remains untouched", encoding="utf-8")
        self.output = self.output_dir / "system.scm"
        self.selection = make_selection()
        self.plan = make_plan(confirmable=True)
        self.plan_path = self.root / "plan.json"
        self.selection_path = self.root / "selection.json"
        self.confirmation_path = self.root / "confirmation.json"
        self._write_inputs()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_inputs(self, *, confirmed: bool = True, target_digest: str | None = None) -> None:
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.selection_path.write_text(
            json.dumps(self.selection.__dict__), encoding="utf-8"
        )
        self.confirmation_path.write_text(
            json.dumps(
                {
                    "confirmed": confirmed,
                    "plan_sha256": self.plan["plan_sha256"],
                    "target_digest": target_digest or self.selection.digest(),
                }
            ),
            encoding="utf-8",
        )

    def _run(self, *, output: Path | None = None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            "--plan", str(self.plan_path),
            "--selection", str(self.selection_path),
            "--confirmation", str(self.confirmation_path),
            "--output", str(output or self.output),
            "--target-mountpoint", str(self.target),
        ]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_confirmed_plan_writes_reviewable_scheme_and_ordered_argv(self) -> None:
        status, stdout, stderr = self._run()

        self.assertEqual(status, 0, stderr)
        manifest = json.loads(stdout)
        self.assertTrue(self.output.is_file())
        self.assertIn("(operating-system", self.output.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["argv"],
            ["guix", "system", "init", str(self.output), str(self.target)],
        )
        self.assertEqual(manifest["executed"], False)
        self.assertEqual(manifest["backend_id"], "guix-system")
        self.assertEqual(
            manifest["configuration_sha256"],
            hashlib.sha256(self.output.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.target_sentinel.read_text(encoding="utf-8"),
            "target remains untouched",
        )
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_diagnostic_plan_is_refused_without_creating_output(self) -> None:
        self.plan = make_plan(confirmable=False)
        self._write_inputs()

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("plan.not_confirmable", stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            self.target_sentinel.read_text(encoding="utf-8"),
            "target remains untouched",
        )

    def test_blocking_critical_device_finding_stops_before_output(self) -> None:
        self.plan["blockers"] = ["critical-device-unresolved"]
        self.plan.pop("plan_sha256", None)
        self.plan["plan_sha256"] = hashlib.sha256(
            canonical_json(self.plan).encode("utf-8")
        ).hexdigest()
        self._write_inputs()

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("plan.blockers", stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            self.target_sentinel.read_text(encoding="utf-8"),
            "target remains untouched",
        )

    def test_confirmation_must_match_the_selected_target(self) -> None:
        self._write_inputs(target_digest="0" * 64)

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("handoff.target_changed", stderr)
        self.assertFalse(self.output.exists())

    def test_explicit_confirmation_is_required(self) -> None:
        self._write_inputs(confirmed=False)

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("confirmed=true", stderr)
        self.assertFalse(self.output.exists())

    def test_configuration_cannot_be_written_inside_target_mount(self) -> None:
        target_output = self.target / "system.scm"

        status, _, stderr = self._run(output=target_output)

        self.assertEqual(status, 2)
        self.assertIn("inside the target mountpoint", stderr)
        self.assertFalse(target_output.exists())
        self.assertEqual(
            self.target_sentinel.read_text(encoding="utf-8"),
            "target remains untouched",
        )

    def test_existing_configuration_is_never_overwritten(self) -> None:
        self.output.write_text("preserve this file", encoding="utf-8")

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("refusing to overwrite", stderr)
        self.assertEqual(
            self.output.read_text(encoding="utf-8"),
            "preserve this file",
        )

    def test_selection_rejects_unknown_fields(self) -> None:
        selection = dict(self.selection.__dict__)
        selection["post_install_command"] = "unexpected"
        self.selection_path.write_text(json.dumps(selection), encoding="utf-8")

        status, _, stderr = self._run()

        self.assertEqual(status, 2)
        self.assertIn("fields must match TargetSelection exactly", stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
