# SPDX-License-Identifier: LicenseRef-Volnist
"""Tests for the read-only WSM installer preflight prototype."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.cli import main
from wsm_install.plan import build_plan, canonical_json

FIXTURES = ROOT / "tests" / "fixtures" / "hardware"


def load_fixture(name: str) -> tuple[dict, bytes]:
    raw = (FIXTURES / name).read_bytes()
    return json.loads(raw), raw


class InstallerPlanTests(unittest.TestCase):
    @staticmethod
    def valid_profile_evidence(report: dict) -> dict:
        return {
            "schema": "wsm-profile-evidence/1",
            "profile": {"vendor": "Test", "model": "Board", "slug": "test/board"},
            "report_id": report["report_id"],
            "report_schema_version": report["schema_version"],
            "isa_level": "x86-64-v1",
            "verified_on": "2026-11-26",
            "verified_by": "WSM test fixture",
            "verified_functions": [{"name": "boot", "status": "pass"}],
            "known_limitations": [],
            "not_assessed": ["suspend/resume"],
        }

    def test_observed_report_emits_deterministic_guix_plan(self) -> None:
        report, raw = load_fixture("desktop-observed.json")
        first, blockers, _ = build_plan(report, raw, "guix")
        second, _, _ = build_plan(report, raw, "guix")
        self.assertEqual(blockers, [])
        self.assertEqual(first, second)
        self.assertEqual(first["backend"]["id"], "guix-system")
        self.assertEqual(first["source_report"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(first["plan_status"], "diagnostic-only")
        self.assertFalse(first["plan_readiness"]["confirmable"])
        self.assertIn("storage-install-target", first["plan_readiness"]["required_user_actions"])
        self.assertTrue(first["execution"]["dry_run"])
        self.assertTrue(first["device_summary"][0]["evidence_refs"])
        self.assertTrue(first["device_summary"][0]["evidence_refs"][0]["json_pointer"].endswith("/evidence/0"))
        digest = first.pop("plan_sha256")
        self.assertEqual(digest, hashlib.sha256(canonical_json(first).encode()).hexdigest())
        self.assertFalse(first["execution"]["mutations_authorized"])
        self.assertFalse(first["execution"]["backend_invoked"])
        self.assertFalse(first["execution"]["disk_access_performed"])

    def test_unknown_critical_display_refuses_to_emit_plan(self) -> None:
        report, raw = load_fixture("unknown-incomplete.json")
        plan, blockers, _ = build_plan(report, raw, "nix")
        self.assertTrue(blockers)
        self.assertEqual(plan["backend"]["id"], "nixos")
        self.assertFalse(plan["execution"]["mutations_authorized"])

    def test_required_network_firmware_error_is_warning_with_offline_fallback(self) -> None:
        report, raw = load_fixture("missing-firmware.json")
        _, blockers, warnings = build_plan(report, raw, "guix")
        self.assertFalse(blockers)
        self.assertTrue(any("required runtime firmware" in item for item in warnings))
        self.assertTrue(any("offline installation may be required" in item for item in warnings))

    def test_profile_evidence_must_match_source_report_identity(self) -> None:
        report, raw = load_fixture("desktop-observed.json")
        evidence = self.valid_profile_evidence(report)
        evidence["report_id"] = "different-report-id-0001"
        _, blockers, _ = build_plan(report, raw, "guix", profile_evidence=evidence)
        self.assertTrue(any("different report_id" in item for item in blockers))

    def test_profile_evidence_must_match_report_schema_version(self) -> None:
        report, raw = load_fixture("desktop-observed.json")
        evidence = self.valid_profile_evidence(report)
        evidence["report_schema_version"] = "9.0.0"
        _, blockers, _ = build_plan(report, raw, "guix", profile_evidence=evidence)
        self.assertTrue(any("report_schema_version does not match" in item for item in blockers))

    def test_cli_accepts_matching_profile_evidence_file(self) -> None:
        report, _ = load_fixture("desktop-observed.json")
        evidence = self.valid_profile_evidence(report)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            evidence_path = root / "evidence.json"
            plan_path = root / "plan.json"
            report_path.write_bytes((FIXTURES / "desktop-observed.json").read_bytes())
            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run", "--profile-evidence", str(evidence_path),
                    "--plan-output", str(plan_path),
                ])
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertTrue(plan_path.is_file())
            self.assertFalse(any("no verified hardware profile" in line for line in stderr.getvalue().splitlines()))

    def test_cli_rejects_unreadable_profile_evidence_without_emitting_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            plan_path = Path(directory) / "plan.json"
            report_path.write_bytes((FIXTURES / "desktop-observed.json").read_bytes())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run", "--profile-evidence", str(Path(directory) / "missing-evidence.json"),
                    "--plan-output", str(plan_path),
                ])
            self.assertEqual(result, 3)
            self.assertIn("profile evidence is unavailable", stderr.getvalue())
            self.assertFalse(plan_path.exists())

    def test_cli_requires_explicit_dry_run_and_preflight(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            main(["--report", str(FIXTURES / "desktop-observed.json"), "--backend", "guix"])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_validates_report_and_writes_only_draft_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            plan_path = Path(directory) / "plan.json"
            report_path.write_bytes((FIXTURES / "desktop-observed.json").read_bytes())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "nix",
                    "--dry-run", "--plan-output", str(plan_path),
                ])
            self.assertEqual(result, 0, stderr.getvalue())
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["backend"]["id"], "nixos")
            self.assertFalse(plan["execution"]["backend_invoked"])
            self.assertFalse(plan["execution"]["disk_access_performed"])
            self.assertFalse(plan["execution"]["plan_confirmable"])
            self.assertTrue(plan["execution"]["dry_run"])


    def test_plan_output_cannot_overwrite_report_or_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_bytes = (FIXTURES / "desktop-observed.json").read_bytes()
            report_path.write_bytes(report_bytes)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run", "--plan-output", str(report_path),
                ])
            self.assertEqual(result, 2)
            self.assertEqual(report_path.read_bytes(), report_bytes)

    def test_plan_output_rejects_hardlink_and_symlink_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_bytes((FIXTURES / "desktop-observed.json").read_bytes())
            hardlink = Path(directory) / "report-hardlink.json"
            symlink = Path(directory) / "report-symlink.json"
            hardlink.hardlink_to(report_path)
            symlink.symlink_to(report_path)
            for alias in (hardlink, symlink):
                with self.subTest(alias=alias.name), contextlib.redirect_stderr(io.StringIO()):
                    result = main([
                        "--preflight", "--report", str(report_path), "--backend", "guix",
                        "--dry-run", "--plan-output", str(alias),
                    ])
                self.assertEqual(result, 2)

    def test_plan_output_rejects_device_nodes(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            result = main([
                "--preflight", "--report", str(FIXTURES / "desktop-observed.json"),
                "--backend", "guix", "--dry-run", "--plan-output", os.devnull,
            ])
        self.assertEqual(result, 2)

    def test_missing_required_roles_make_plan_diagnostic_only(self) -> None:
        report, raw = load_fixture("desktop-observed.json")
        plan, blockers, warnings = build_plan(report, raw, "guix")
        self.assertEqual(blockers, [])
        self.assertFalse(plan["plan_readiness"]["confirmable"])
        self.assertEqual(plan["plan_readiness"]["role_coverage"]["input"], "not-collected")
        self.assertEqual(plan["plan_readiness"]["role_coverage"]["boot-path"], "not-collected")
        self.assertTrue(any("storage target is not selected" in item for item in warnings))

    def test_cli_rejects_malformed_json_without_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "bad.json"
            plan_path = Path(directory) / "plan.json"
            report_path.write_text("{broken", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run", "--plan-output", str(plan_path),
                ])
            self.assertEqual(result, 2)
            self.assertFalse(plan_path.exists())

    def test_cli_rejects_unknown_or_invalid_schema_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "bad-schema.json"
            report = json.loads((FIXTURES / "desktop-observed.json").read_text())
            report["schema_version"] = "9.0.0"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run",
                ])
            self.assertEqual(result, 2)

    def test_offline_mode_is_enforced_by_report_contract(self) -> None:
        report, _ = load_fixture("desktop-observed.json")
        report["privacy"]["network_requests_performed"] = True
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "network.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                result = main([
                    "--preflight", "--report", str(report_path), "--backend", "guix",
                    "--dry-run",
                ])
            self.assertEqual(result, 2)

    def test_not_detected_critical_device_refuses_to_emit_plan(self) -> None:
        report, raw = load_fixture("unknown-incomplete.json")
        report["devices"][0]["discovery_status"] = "not-detected"
        _, blockers, _ = build_plan(report, raw, "nix")
        self.assertTrue(any("not-detected" in item for item in blockers))

if __name__ == "__main__":
    unittest.main()
