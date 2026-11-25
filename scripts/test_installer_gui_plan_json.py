#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Verify Qt and Python produce identical canonical plan JSON and digests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.plan import build_plan, canonical_json  # noqa: E402


def invoke(binary: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    return subprocess.run(
        [str(binary), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
    )


def write_plan(path: Path, plan: dict) -> None:
    path.write_text(canonical_json(plan), encoding="utf-8")


def refresh_plan_digest(plan: dict) -> None:
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    plan["plan_sha256"] = hashlib.sha256(
        canonical_json(unhashed).encode("utf-8")
    ).hexdigest()


def expect_rejected(binary: Path, plan_path: Path, report_path: Path, reason: str) -> None:
    result = invoke(binary, "--validate-plan", str(plan_path), "--report", str(report_path))
    if result.returncode == 0:
        raise AssertionError(f"{reason}: Qt validator accepted an invalid plan")
    if result.returncode != 3:
        raise AssertionError(
            f"{reason}: expected validation exit 3, got {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_installer_gui_plan_json.py PATH_TO_WSM_INSTALLER")
    binary = Path(sys.argv[1]).resolve()
    if not binary.is_file():
        raise SystemExit(f"WSM installer binary does not exist: {binary}")

    fixture_path = ROOT / "installer/gui/tests/fixtures/canonical-json.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    expected = canonical_json(fixture).encode("utf-8")
    result = invoke(binary, "--canonical-json", str(fixture_path))
    if result.returncode != 0:
        raise AssertionError(
            "Qt canonical JSON helper failed: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    if result.stdout != expected:
        raise AssertionError(
            "Qt canonical JSON bytes differ from Python canonical_json().\n"
            f"Qt:     {result.stdout!r}\nPython: {expected!r}"
        )
    if hashlib.sha256(result.stdout).digest() != hashlib.sha256(expected).digest():
        raise AssertionError("Qt/Python canonical JSON SHA-256 digest mismatch")

    report_path = ROOT / "tests/fixtures/hardware/desktop-observed.json"
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    plan, _blockers, _warnings = build_plan(report, report_bytes, "guix")

    with tempfile.TemporaryDirectory(prefix="wsm-plan-json-parity-") as temporary:
        temporary_dir = Path(temporary)
        plan_path = temporary_dir / "plan.json"
        active_report_path = temporary_dir / "report.json"
        active_report_path.write_bytes(report_bytes)
        write_plan(plan_path, plan)

        valid = invoke(
            binary, "--validate-plan", str(plan_path), "--report", str(active_report_path)
        )
        if valid.returncode != 0:
            raise AssertionError(
                "Qt rejected the Python-produced diagnostic plan: "
                + valid.stderr.decode("utf-8", errors="replace")
            )

        tampered_body = copy.deepcopy(plan)
        tampered_body["warnings"].append("підміна після обчислення digest")
        write_plan(plan_path, tampered_body)
        expect_rejected(binary, plan_path, active_report_path, "tampered plan body")

        write_plan(plan_path, plan)
        active_report_path.write_bytes(report_bytes + b"\n")
        expect_rejected(binary, plan_path, active_report_path, "changed report bytes")

        active_report_path.write_bytes(report_bytes)
        wrong_id = copy.deepcopy(plan)
        wrong_id["source_report"]["report_id"] = "different-report-id"
        refresh_plan_digest(wrong_id)
        write_plan(plan_path, wrong_id)
        expect_rejected(binary, plan_path, active_report_path, "wrong source report id")

        wrong_schema = copy.deepcopy(plan)
        wrong_schema["source_report"]["schema_version"] = "99.0.0"
        refresh_plan_digest(wrong_schema)
        write_plan(plan_path, wrong_schema)
        expect_rejected(binary, plan_path, active_report_path, "wrong source schema version")

    print("PASS: Qt and Python canonical JSON bytes/SHA-256 match; tampering is rejected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
