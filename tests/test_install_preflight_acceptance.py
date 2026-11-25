# SPDX-License-Identifier: LicenseRef-Volnist
"""Black-box acceptance tests for the read-only wsm-install CLI contract."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "hardware"

from wsm_install.cli import main
from wsm_install.plan import canonical_json


class InstallerCliAcceptanceTests(unittest.TestCase):
    def run_cli(self, report: Path, *extra: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main([
                "--preflight",
                "--report", str(report),
                "--backend", "guix",
                "--dry-run",
                *extra,
            ])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_missing_report_returns_usage_error_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "missing.json"
            plan = Path(directory) / "plan.json"
            result, stdout, stderr = self.run_cli(report, "--plan-output", str(plan))
            self.assertEqual(result, 2)
            self.assertEqual(stdout, "")
            self.assertIn("cannot read report", stderr)
            self.assertFalse(plan.exists())

    def test_critical_unknown_returns_exit_three_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            report = FIXTURES / "unknown-incomplete.json"
            result, stdout, stderr = self.run_cli(report, "--plan-output", str(plan))
            self.assertEqual(result, 3)
            self.assertEqual(stdout, "")
            self.assertIn("no plan emitted", stderr)
            self.assertFalse(plan.exists())

    def test_non_object_json_is_rejected_before_plan_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "array.json"
            plan = Path(directory) / "plan.json"
            report.write_text("[]", encoding="utf-8")
            result, stdout, stderr = self.run_cli(report, "--plan-output", str(plan))
            self.assertEqual(result, 2)
            self.assertEqual(stdout, "")
            self.assertIn("top-level value must be an object", stderr)
            self.assertFalse(plan.exists())

    def test_invalid_schema_file_is_rejected_before_plan_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "invalid-schema.json"
            plan = Path(directory) / "plan.json"
            schema.write_text("{broken", encoding="utf-8")
            report = FIXTURES / "desktop-observed.json"
            result, stdout, stderr = self.run_cli(
                report, "--schema", str(schema), "--plan-output", str(plan)
            )
            self.assertEqual(result, 2)
            self.assertEqual(stdout, "")
            self.assertIn("cannot load hardware report schema", stderr)
            self.assertFalse(plan.exists())

    def test_stdout_is_only_canonical_plan_json_and_summary_uses_stderr(self) -> None:
        report = FIXTURES / "desktop-observed.json"
        result, stdout, stderr = self.run_cli(report)
        self.assertEqual(result, 0, stderr)
        plan = json.loads(stdout)
        self.assertEqual(stdout, canonical_json(plan) + "\n")
        self.assertEqual(plan["backend"]["id"], "guix-system")
        self.assertIn("WSM hardware preflight", stderr)
        self.assertNotIn("WSM hardware preflight", stdout)

    def test_quiet_suppresses_human_summary_without_changing_plan(self) -> None:
        report = FIXTURES / "desktop-observed.json"
        normal_result, normal_stdout, _ = self.run_cli(report)
        quiet_result, quiet_stdout, quiet_stderr = self.run_cli(report, "--quiet")
        self.assertEqual(normal_result, 0)
        self.assertEqual(quiet_result, 0)
        self.assertEqual(normal_stdout, quiet_stdout)
        self.assertNotIn("WSM hardware preflight", quiet_stderr)

    def test_stdout_and_explicit_plan_file_are_byte_identical(self) -> None:
        report = FIXTURES / "desktop-observed.json"
        stdout_result, stdout_plan, _ = self.run_cli(report, "--quiet")
        self.assertEqual(stdout_result, 0)
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.json"
            file_result, file_stdout, _ = self.run_cli(
                report, "--quiet", "--plan-output", str(plan_path)
            )
            self.assertEqual(file_result, 0)
            self.assertEqual(file_stdout, "")
            self.assertEqual(plan_path.read_text(encoding="utf-8"), stdout_plan)

    def test_report_bytes_are_not_modified_by_normal_plan_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            original = (FIXTURES / "desktop-observed.json").read_bytes()
            report.write_bytes(original)
            plan = Path(directory) / "plan.json"
            result, _, stderr = self.run_cli(report, "--plan-output", str(plan))
            self.assertEqual(result, 0, stderr)
            self.assertEqual(report.read_bytes(), original)
            self.assertTrue(plan.is_file())

    def test_plan_digest_covers_canonical_plan_without_digest_field(self) -> None:
        result, stdout, stderr = self.run_cli(FIXTURES / "desktop-observed.json", "--quiet")
        self.assertEqual(result, 0, stderr)
        plan = json.loads(stdout)
        digest = plan.pop("plan_sha256")
        calculated = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
        self.assertEqual(digest, calculated)
        self.assertEqual(
            plan["source_report"]["sha256"],
            hashlib.sha256((FIXTURES / "desktop-observed.json").read_bytes()).hexdigest(),
        )

    def test_optional_unknown_device_remains_in_plan_without_blocking(self) -> None:
        report = json.loads((FIXTURES / "desktop-observed.json").read_text(encoding="utf-8"))
        optional = copy.deepcopy(report["devices"][0])
        optional["device_id"] = "optional-unknown-test-device"
        optional["criticality"] = ["optional-peripheral"]
        optional["discovery_status"] = "unknown"
        optional["driver"]["status"] = "unknown"
        optional["firmware"]["requirement"] = "unknown"
        optional["firmware"]["runtime_status"] = "unknown"
        report["devices"].append(optional)

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            result, stdout, stderr = self.run_cli(report_path, "--quiet")
            self.assertEqual(result, 0, stderr)
            plan = json.loads(stdout)
            unknown = next(
                item for item in plan["device_summary"]
                if item["device_id"] == "optional-unknown-test-device"
            )
            self.assertEqual(unknown["discovery_status"], "unknown")
            self.assertFalse(plan["execution"]["mutations_authorized"])
            self.assertFalse(plan["execution"]["backend_invoked"])
            self.assertFalse(plan["execution"]["disk_access_performed"])

    def test_dry_run_does_not_invoke_process_or_network_apis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            with (
                patch("subprocess.run") as run,
                patch("subprocess.Popen") as popen,
                patch("socket.create_connection") as connect,
                patch("socket.socket") as socket_ctor,
            ):
                result, _, stderr = self.run_cli(
                    FIXTURES / "desktop-observed.json",
                    "--quiet",
                    "--plan-output", str(plan),
                )
            self.assertEqual(result, 0, stderr)
            run.assert_not_called()
            popen.assert_not_called()
            connect.assert_not_called()
            socket_ctor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
