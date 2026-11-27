# SPDX-License-Identifier: LicenseRef-Volnist
"""Guix-only offscreen behavior tests for the optional PySide6/Kirigami preview.

Guix-only offscreen behavior test. Kept under tests/guix so ordinary
minimal unittest discovery does not import Qt, while the pinned Guix target
runs it with the exact Qt/Kirigami closure.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from wsm_installer.controller import PreviewController
from wsm_install.plan import canonical_json

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
QML = ROOT / "wsm_installer" / "qml" / "Main.qml"


def fresh_report() -> dict:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    report["collected_at"] = now.isoformat().replace("+00:00", "Z")
    return report


def make_disk_inventory(root: Path) -> None:
    device = root / "sda"
    (device / "device").mkdir(parents=True)
    (device / "size").write_text("2097152\n", encoding="utf-8")
    (device / "removable").write_text("0\n", encoding="utf-8")
    (device / "device" / "vendor").write_text("TEST\n", encoding="utf-8")
    (device / "device" / "model").write_text("Synthetic Test Disk\n", encoding="utf-8")


class InstallerQmlNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.block = self.root / "block"
        self.block.mkdir()
        make_disk_inventory(self.block)

        self.controller = PreviewController(
            collector=lambda *_args, **_kwargs: fresh_report(),
            sysfs_root=self.root / "sys",
            proc_root=self.root / "proc",
            sys_block_root=self.block,
        )
        self.engine = QQmlApplicationEngine()
        for variable in ("QML_IMPORT_PATH", "QML2_IMPORT_PATH"):
            for path in os.environ.get(variable, "").split(os.pathsep):
                if path:
                    self.engine.addImportPath(path)
        self.engine.rootContext().setContextProperty("wsmController", self.controller)
        self.engine.load(QUrl.fromLocalFile(str(QML)))
        self.assertTrue(self.engine.rootObjects(), "Kirigami QML failed to load")
        self.window = self.engine.rootObjects()[0]
        self.next_button = self.window.findChild(QObject, "wsm-installer-next")
        self.assertIsNotNone(self.next_button, "next navigation button is missing")

        self.controller.refresh()
        self.app.processEvents()

    def tearDown(self) -> None:
        if self.engine.rootObjects():
            self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def _advance(self) -> None:
        self.app.processEvents()
        self.assertTrue(self.next_button.property("enabled"), "next step must be gated by controller state")
        self.next_button.click()
        self.app.processEvents()

    def _open_disk_step(self) -> None:
        self.assertEqual(self.window.property("step"), 0)
        self._advance()
        self.assertEqual(self.window.property("step"), 1)
        self._advance()
        self.assertEqual(self.window.property("step"), 2)

    def test_welcome_evidence_disks_review_navigation_requires_selected_disk(self) -> None:
        self._open_disk_step()
        self.assertFalse(self.controller.canReview)
        self.assertFalse(self.next_button.property("enabled"))

        self.controller.selectDisk("/dev/sda")
        self.app.processEvents()
        self.assertTrue(self.controller.canReview)
        self._advance()

        self.assertEqual(self.window.property("step"), 3)
        self.assertTrue(self.controller.reviewed)
        self.assertIn("Synthetic Test Disk", self.controller.status)

    def test_target_identity_drift_keeps_review_on_disk_step(self) -> None:
        self._open_disk_step()
        self.controller.selectDisk("/dev/sda")
        self.app.processEvents()
        self.assertTrue(self.next_button.property("enabled"))

        (self.block / "sda" / "device" / "model").write_text(
            "Replaced Disk\n", encoding="utf-8"
        )
        self.next_button.click()
        self.app.processEvents()

        self.assertEqual(self.window.property("step"), 2)
        self.assertEqual(self.controller.state, "target-changed")
        self.assertFalse(self.controller.reviewed)
        self.assertFalse(self.controller.canReview)

    def test_missing_disk_inventory_blocks_review(self) -> None:
        self.controller._sys_block_root = self.root / "missing-block"
        self.controller.refresh()
        self.app.processEvents()
        self._open_disk_step()

        self.assertEqual(self.controller.diskInventoryState, "unavailable")
        self.assertFalse(self.controller.canReview)
        self.assertFalse(self.next_button.property("enabled"))

    def test_stale_report_blocks_navigation(self) -> None:
        def stale_collector(*_args, **_kwargs):
            report = fresh_report()
            report["collected_at"] = "2000-01-01T00:00:00Z"
            return report

        self.controller._collector = stale_collector
        self.controller.refresh()
        self.app.processEvents()

        self.assertEqual(self.controller.state, "stale")
        self.assertEqual(self.controller.devices, [])
        self.assertFalse(self.next_button.property("enabled"))

    def test_failed_refresh_clears_previous_report_and_target(self) -> None:
        self.controller.selectDisk("/dev/sda")
        self.assertEqual(self.controller.selectedDisk, "/dev/sda")
        self.assertTrue(self.controller.disks)

        def failed_collector(*_args, **_kwargs):
            raise OSError("synthetic collector failure")

        self.controller._collector = failed_collector
        self.controller.refresh()
        self.app.processEvents()

        self.assertEqual(self.controller.state, "invalid")
        self.assertEqual(self.controller.reportId, "")
        self.assertEqual(self.controller.devices, [])
        self.assertEqual(self.controller.disks, [])
        self.assertEqual(self.controller.selectedDisk, "")
        self.assertEqual(self.controller.diskInventoryState, "not-run")
        self.assertFalse(self.controller.canReview)
        self.assertFalse(self.controller.reviewed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
