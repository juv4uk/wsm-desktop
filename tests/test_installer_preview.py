# SPDX-License-Identifier: LicenseRef-Volnist
"""Pure tests for the read-only PySide/Kirigami installer preview core."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from wsm_installer.preview import (
    DiskInventoryError,
    StaleReportError,
    TargetIdentityChangedError,
    build_preview,
    enumerate_disk_targets,
    revalidate_disk_target,
)
from wsm_install.plan import canonical_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"


def current_fixture() -> tuple[bytes, dt.datetime]:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = dt.datetime(2026, 11, 28, 12, 0, tzinfo=dt.timezone.utc)
    report["collected_at"] = now.isoformat().replace("+00:00", "Z")
    return canonical_json(report).encode("utf-8"), now


class InstallerPreviewTests(unittest.TestCase):
    def test_exact_source_digest_and_diagnostic_plan_flags(self) -> None:
        raw, now = current_fixture()
        preview = build_preview(raw, now=now)
        self.assertEqual(preview.report_sha256, preview.plan["source_report"]["sha256"])
        self.assertEqual(preview.plan["execution"], {
            "dry_run": True,
            "plan_confirmable": False,
            "mutations_authorized": False,
            "backend_invoked": False,
            "disk_access_performed": False,
        })
        unhashed = dict(preview.plan)
        digest = unhashed.pop("plan_sha256")
        expected = hashlib.sha256(canonical_json(unhashed).encode("utf-8")).hexdigest()
        self.assertEqual(digest, expected)

    def test_unknown_gpu_evidence_is_preserved_not_promoted(self) -> None:
        raw, now = current_fixture()
        report = json.loads(raw)
        gpu = next(device for device in report["devices"] if device["category"] == "gpu")
        gpu["discovery_status"] = "unknown"
        gpu["driver"]["status"] = "unknown"
        gpu["firmware"]["runtime_status"] = "unknown"
        unknown_raw = canonical_json(report).encode("utf-8")
        preview = build_preview(unknown_raw, now=now)
        gpu_view = next(device for device in preview.report["devices"] if device["category"] == "gpu")
        self.assertEqual(gpu_view["discovery_status"], "unknown")
        self.assertEqual(gpu_view["driver"]["status"], "unknown")
        self.assertEqual(gpu_view["firmware"]["runtime_status"], "unknown")

    def test_malformed_and_schema_invalid_reports_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_preview(b'{"schema_version":')
        raw, now = current_fixture()
        report = json.loads(raw)
        report.pop("privacy", None)
        with self.assertRaises(ValueError):
            build_preview(canonical_json(report).encode("utf-8"), now=now)

    def test_stale_and_future_reports_fail_closed(self) -> None:
        raw, now = current_fixture()
        with self.assertRaises(StaleReportError):
            build_preview(raw, now=now + dt.timedelta(minutes=11))
        report = json.loads(raw)
        report["collected_at"] = (now + dt.timedelta(hours=1)).isoformat()
        with self.assertRaises(StaleReportError):
            build_preview(canonical_json(report).encode("utf-8"), now=now)

    def test_disk_inventory_uses_sysfs_and_revalidates_changed_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "sda"
            (device / "device").mkdir(parents=True)
            (device / "size").write_text("2048\n", encoding="utf-8")
            (device / "removable").write_text("0\n", encoding="utf-8")
            (device / "device" / "vendor").write_text("ATA\n", encoding="utf-8")
            (device / "device" / "model").write_text("Example SSD\n", encoding="utf-8")
            targets = enumerate_disk_targets(root)
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].path, "/dev/sda")
            self.assertEqual(revalidate_disk_target(targets[0], root), targets[0])
            (device / "device" / "model").write_text("Different SSD\n", encoding="utf-8")
            with self.assertRaises(TargetIdentityChangedError):
                revalidate_disk_target(targets[0], root)

    def test_missing_sysfs_inventory_is_not_reported_as_no_disks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "not-present"
            with self.assertRaises(DiskInventoryError):
                enumerate_disk_targets(missing)
