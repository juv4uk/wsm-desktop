# SPDX-License-Identifier: LicenseRef-Volnist
"""Pure, read-only report, plan, and disk-identity helpers for the GUI."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wsm_install.guided import list_disks
from wsm_install.plan import build_plan, canonical_json, summarize_report
from wsm_install.validation import (
    DEFAULT_SCHEMA,
    require_valid_report,
)


DEFAULT_MAX_REPORT_AGE = dt.timedelta(minutes=10)
MAX_FUTURE_CLOCK_SKEW = dt.timedelta(seconds=60)


class MalformedReportError(ValueError):
    """The collector supplied malformed UTF-8 JSON or a non-object value."""


class StaleReportError(ValueError):
    """The report is older than the approved preview window or from the future."""


class DiskInventoryError(RuntimeError):
    """The read-only sysfs disk inventory is unavailable."""


class TargetIdentityChangedError(RuntimeError):
    """A selected disk no longer matches the current read-only inventory."""


@dataclass(frozen=True)
class Preview:
    report: dict[str, Any]
    report_sha256: str
    summary: str
    plan: dict[str, Any]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class DiskTarget:
    """Non-serial sysfs identity used only for the current preview session."""

    path: str
    size_bytes: int
    removable: bool
    model: str
    vendor: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "removable": self.removable,
            "model": self.model or "невідома модель",
            "vendor": self.vendor or "невідомий виробник",
        }

    @property
    def identity(self) -> tuple[str, int, bool, str, str]:
        return (self.path, self.size_bytes, self.removable, self.model, self.vendor)


def _parse_timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise StaleReportError("у звіті немає коректного collected_at")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StaleReportError("у звіті некоректний collected_at") from exc
    if parsed.tzinfo is None:
        raise StaleReportError("collected_at мусить містити часовий пояс")
    return parsed.astimezone(dt.timezone.utc)


def build_preview(
    report_bytes: bytes,
    *,
    schema_path: str | Path = DEFAULT_SCHEMA,
    now: dt.datetime | None = None,
    max_age: dt.timedelta = DEFAULT_MAX_REPORT_AGE,
) -> Preview:
    """Validate exact report bytes, enforce freshness, and reuse the typed plan API."""
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedReportError(f"апаратний звіт не є коректним UTF-8 JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise MalformedReportError("верхній рівень апаратного звіту мусить бути JSON object")

    require_valid_report(report, schema_path)
    collected_at = _parse_timestamp(report.get("collected_at"))
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    age = current - collected_at
    if age < -MAX_FUTURE_CLOCK_SKEW:
        raise StaleReportError("час звіту суттєво випереджає системний час; перегляд заблоковано")
    if age > max_age:
        raise StaleReportError(
            f"звіт застарів: вік {int(age.total_seconds())} с перевищує ліміт "
            f"{int(max_age.total_seconds())} с"
        )

    plan, blockers, warnings = build_plan(report, report_bytes, "guix")
    return Preview(
        report=report,
        report_sha256=plan["source_report"]["sha256"],
        summary=summarize_report(report),
        plan=plan,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def enumerate_disk_targets(sys_block_root: str | Path = "/sys/block") -> tuple[DiskTarget, ...]:
    """Use the existing WSM read-only whole-disk provider; never open /dev nodes."""
    root = Path(sys_block_root)
    if not root.is_dir():
        raise DiskInventoryError("sysfs /block недоступний; список накопичувачів не перевірено")

    try:
        candidates = list_disks(root)
    except OSError as exc:
        raise DiskInventoryError(f"не вдалося прочитати sysfs /block: {exc}") from exc

    targets: list[DiskTarget] = []
    for candidate in candidates:
        name = Path(candidate.path).name
        device = root / name / "device"
        targets.append(
            DiskTarget(
                path=candidate.path,
                size_bytes=candidate.size_bytes,
                removable=candidate.removable,
                model=_read_text(device / "model"),
                vendor=_read_text(device / "vendor"),
            )
        )
    return tuple(targets)


def revalidate_disk_target(
    selected: DiskTarget,
    sys_block_root: str | Path = "/sys/block",
) -> DiskTarget:
    """Re-read the provider inventory and refuse a changed or missing target."""
    current = enumerate_disk_targets(sys_block_root)
    match = next((item for item in current if item.path == selected.path), None)
    if match is None:
        raise TargetIdentityChangedError(
            f"{selected.path} більше не присутній у поточному списку накопичувачів"
        )
    if match.identity != selected.identity:
        raise TargetIdentityChangedError(
            f"ідентичність {selected.path} змінилася після вибору; повторний перегляд потрібен"
        )
    return match


def canonical_report_bytes(report: dict[str, Any]) -> bytes:
    """Serialize an in-memory collector report deterministically for provenance."""
    return canonical_json(report).encode("utf-8")
