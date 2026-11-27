# SPDX-License-Identifier: LicenseRef-Volnist
"""Typed Qt bridge for the read-only WSM hardware preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Property, Signal, Slot

from wsm_hwcheck.collector import collect_report
from wsm_installer.preview import (
    DiskInventoryError,
    DiskTarget,
    MalformedReportError,
    StaleReportError,
    TargetIdentityChangedError,
    build_preview,
    canonical_report_bytes,
    enumerate_disk_targets,
    revalidate_disk_target,
)
from wsm_install.validation import ReportSchemaError, SchemaUnavailableError


class PreviewController(QObject):
    """Expose validated evidence and a diagnostic plan; it cannot apply them."""

    stateChanged = Signal()
    statusChanged = Signal()
    errorChanged = Signal()
    reportChanged = Signal()
    disksChanged = Signal()
    selectedDiskChanged = Signal()
    reviewChanged = Signal()

    def __init__(
        self,
        *,
        collector: Callable[..., dict[str, Any]] = collect_report,
        sysfs_root: str | Path = "/sys",
        proc_root: str | Path = "/proc",
        sys_block_root: str | Path = "/sys/block",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._collector = collector
        self._sysfs_root = Path(sysfs_root)
        self._proc_root = Path(proc_root)
        self._sys_block_root = Path(sys_block_root)
        self._state = "idle"
        self._status = "Готово до локальної перевірки."
        self._error = ""
        self._summary = ""
        self._report_id = ""
        self._collected_at = ""
        self._report_sha256 = ""
        self._plan_sha256 = ""
        self._devices: list[dict[str, Any]] = []
        self._warnings: list[str] = []
        self._blockers: list[str] = []
        self._disks: tuple[DiskTarget, ...] = ()
        self._disk_inventory_state = "not-run"
        self._selected_disk: DiskTarget | None = None
        self._reviewed = False

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(str, notify=reportChanged)
    def summary(self) -> str:
        return self._summary

    @Property(str, notify=reportChanged)
    def reportId(self) -> str:
        return self._report_id

    @Property(str, notify=reportChanged)
    def collectedAt(self) -> str:
        return self._collected_at

    @Property(str, notify=reportChanged)
    def reportSha256(self) -> str:
        return self._report_sha256

    @Property(str, notify=reportChanged)
    def planSha256(self) -> str:
        return self._plan_sha256

    @Property("QVariantList", notify=reportChanged)
    def devices(self) -> list[dict[str, Any]]:
        return self._devices

    @Property("QVariantList", notify=reportChanged)
    def warnings(self) -> list[str]:
        return self._warnings

    @Property("QVariantList", notify=reportChanged)
    def blockers(self) -> list[str]:
        return self._blockers

    @Property("QVariantList", notify=disksChanged)
    def disks(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self._disks]

    @Property(str, notify=disksChanged)
    def diskInventoryState(self) -> str:
        return self._disk_inventory_state

    @Property(str, notify=selectedDiskChanged)
    def selectedDisk(self) -> str:
        return self._selected_disk.path if self._selected_disk else ""

    @Property(bool, notify=reviewChanged)
    def reviewed(self) -> bool:
        return self._reviewed

    @Property(bool, notify=stateChanged)
    def canReview(self) -> bool:
        return self._state == "ready" and self._disk_inventory_state == "loaded"

    def _set_state(self, value: str) -> None:
        if self._state != value:
            self._state = value
            self.stateChanged.emit()

    def _set_status(self, value: str) -> None:
        if self._status != value:
            self._status = value
            self.statusChanged.emit()

    def _set_error(self, value: str) -> None:
        if self._error != value:
            self._error = value
            self.errorChanged.emit()

    @staticmethod
    def _device_view(device: dict[str, Any]) -> dict[str, Any]:
        identity = device.get("identity", {})
        driver = device.get("driver", {})
        firmware = device.get("firmware", {})
        tests = device.get("functional_tests", [])
        evidence = device.get("evidence", [])
        label = identity.get("model") or identity.get("manufacturer") or device.get("device_id", "unknown")
        evidence_summary = (
            evidence[0].get("summary", "джерело не уточнене")
            if evidence and isinstance(evidence[0], dict)
            else "докази відсутні"
        )
        return {
            "deviceId": device.get("device_id", "unknown"),
            "category": device.get("category", "unknown"),
            "label": label,
            "discoveryStatus": device.get("discovery_status", "unknown"),
            "driverStatus": driver.get("status", "unknown"),
            "boundDriver": driver.get("bound_driver", "unknown"),
            "firmwareRequirement": firmware.get("requirement", "unknown"),
            "firmwareStatus": firmware.get("runtime_status", "unknown"),
            "functionalTests": [
                {
                    "capability": test.get("capability", "unknown"),
                    "status": test.get("status", "unknown"),
                }
                for test in tests if isinstance(test, dict)
            ],
            "evidence": evidence_summary,
        }

    @Slot()
    def refresh(self) -> None:
        """Collect local sysfs/procfs facts only; no subprocess or privilege."""
        self._reviewed = False
        self.reviewChanged.emit()
        self._set_state("loading")
        self._set_error("")
        self._set_status("Збираємо локальні апаратні відомості лише для читання.")
        try:
            report = self._collector(
                self._sysfs_root,
                self._proc_root,
                include_runtime_diagnostics=False,
            )
            report_bytes = canonical_report_bytes(report)
            preview = build_preview(report_bytes)
            self._summary = preview.summary
            self._report_id = str(report.get("report_id", "unknown"))
            self._collected_at = str(report.get("collected_at", "unknown"))
            self._report_sha256 = preview.report_sha256
            self._plan_sha256 = str(preview.plan.get("plan_sha256", ""))
            self._devices = [self._device_view(item) for item in report.get("devices", [])]
            self._warnings = list(preview.warnings)
            self._blockers = list(preview.blockers)
        except StaleReportError as exc:
            self._clear_report()
            self._set_state("stale")
            self._set_error(str(exc))
            self._set_status("Звіт застарів або має некоректний час; перегляд заблоковано.")
            self.reportChanged.emit()
            return
        except (MalformedReportError, ReportSchemaError, SchemaUnavailableError, OSError, ValueError) as exc:
            self._clear_report()
            self._set_state("invalid")
            self._set_error(str(exc))
            self._set_status("Звіт не пройшов перевірку; перегляд заблоковано.")
            self.reportChanged.emit()
            return
        except Exception as exc:
            self._clear_report()
            self._set_state("invalid")
            self._set_error(f"неочікувана помилка read-only preflight: {exc}")
            self._set_status("Перегляд заблоковано.")
            self.reportChanged.emit()
            return

        try:
            self._disks = enumerate_disk_targets(self._sys_block_root)
            self._disk_inventory_state = "loaded"
        except DiskInventoryError as exc:
            self._disks = ()
            self._disk_inventory_state = "unavailable"
            self._set_error(str(exc))
        self._selected_disk = None
        self.disksChanged.emit()
        self.selectedDiskChanged.emit()
        self.reportChanged.emit()
        self._set_state("ready")
        self._set_status(
            "Звіт і діагностичний план перевірено. Усі дії з накопичувачами та APPLY вимкнені."
        )

    def _clear_report(self) -> None:
        self._summary = ""
        self._report_id = ""
        self._collected_at = ""
        self._report_sha256 = ""
        self._plan_sha256 = ""
        self._devices = []
        self._warnings = []
        self._blockers = []

    @Slot(str)
    def selectDisk(self, path: str) -> None:
        candidate = next((item for item in self._disks if item.path == path), None)
        if candidate is None:
            self._set_error("Можна вибрати лише диск із поточного read-only списку.")
            return
        self._selected_disk = candidate
        self._reviewed = False
        self.selectedDiskChanged.emit()
        self.reviewChanged.emit()
        self._set_error("")

    @Slot()
    def clearDiskSelection(self) -> None:
        self._selected_disk = None
        self._reviewed = False
        self.selectedDiskChanged.emit()
        self.reviewChanged.emit()

    @Slot(result=bool)
    def review(self) -> bool:
        """Re-enumerate the chosen target; only confirm its read-only preview."""
        if not self.canReview:
            self._set_error("Звіт або інвентаризація дисків не пройшли перевірку.")
            return False
        if self._selected_disk is not None:
            try:
                revalidate_disk_target(self._selected_disk, self._sys_block_root)
            except (DiskInventoryError, TargetIdentityChangedError) as exc:
                self._reviewed = False
                self._set_state("target-changed")
                self._set_error(str(exc))
                self._set_status("Ідентичність цілі змінилася; перегляд заблоковано.")
                self.reviewChanged.emit()
                return False
        self._reviewed = True
        self.reviewChanged.emit()
        self._set_error("")
        self._set_status("Підтверджено лише перегляд. Система не встановлювалася; диск не змінювався.")
        return True
