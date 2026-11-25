# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the isolated wsm-hwcheck QEMU guest runner."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ci_run_hwcheck_guest import (  # noqa: E402
    REPORT_BEGIN,
    REPORT_END,
    build_qemu_command,
    extract_hardware_report,
    validate_hardware_report,
)


class QemuHwcheckGuestTests(unittest.TestCase):
    def test_extract_report_ignores_boot_log_and_guest_poweroff_noise(self) -> None:
        payload = b'{"schema_version":"1.0.0","devices":[]}'
        serial = (
            b"Linux version synthetic\r\nboot messages\r\n"
            + REPORT_BEGIN
            + b"\r\n"
            + payload
            + b"\r\n"
            + REPORT_END
            + b"\r\nWSM_HWCHECK_GUEST_DONE\r\n"
        )
        self.assertEqual(extract_hardware_report(serial), payload)

    def test_extract_report_rejects_missing_or_duplicate_boundaries(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            extract_hardware_report(b"boot only")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            extract_hardware_report(REPORT_BEGIN + b"{}" + REPORT_END + REPORT_BEGIN)

    def test_qemu_command_is_tcg_only_and_has_no_disk_or_host_passthrough(self) -> None:
        command = build_qemu_command(
            "qemu-system-x86_64",
            Path("/tmp/guest-kernel"),
            Path("/tmp/guest-initramfs.cpio.gz"),
        )
        self.assertEqual(command[command.index("-machine") + 1], "q35,accel=tcg")
        self.assertEqual(command[command.index("-nic") + 1], "none")
        self.assertEqual(command[command.index("-serial") + 1], "stdio")
        self.assertIn("-kernel", command)
        self.assertIn("-initrd", command)
        forbidden = {
            "-drive", "-blockdev", "-device", "-netdev", "-fsdev",
            "-virtfs", "-pflash", "-bios",
        }
        self.assertTrue(forbidden.isdisjoint(command))

    def test_current_observed_fixture_passes_schema_and_read_only_invariants(self) -> None:
        report = json.loads(
            (ROOT / "tests/fixtures/hardware/desktop-observed.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas/hardware-report.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validate_hardware_report(report, schema), len(report["devices"]))

    def test_report_with_network_activity_is_rejected(self) -> None:
        report = json.loads(
            (ROOT / "tests/fixtures/hardware/desktop-observed.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas/hardware-report.schema.json").read_text(encoding="utf-8")
        )
        report["privacy"]["network_requests_performed"] = True
        with self.assertRaisesRegex(ValueError, "network_requests_performed=false"):
            validate_hardware_report(report, schema)

    def test_inventory_only_report_cannot_claim_functional_success(self) -> None:
        report = json.loads(
            (ROOT / "tests/fixtures/hardware/desktop-observed.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas/hardware-report.schema.json").read_text(encoding="utf-8")
        )
        report["devices"][0]["functional_tests"] = [
            {"capability": "display-output", "status": "passed"}
        ]
        with self.assertRaisesRegex(ValueError, "unexecuted status"):
            validate_hardware_report(report, schema)


if __name__ == "__main__":
    unittest.main()
