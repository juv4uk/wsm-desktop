# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure, fail-closed report freshness policy (proposal; not wired into CLI yet).

The schema/collector contract is owned by the hardware producer workstream.
This module tests the consumer-side decision rules without changing schema v1.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

DEFAULT_MAX_AGE_SECONDS = 600
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOT_DOMAIN = b"wsm-desktop/boot-session/v1\0"
_TOPOLOGY_FIELDS = (
    "vendor_id",
    "device_id",
    "subsystem_vendor_id",
    "subsystem_device_id",
    "revision",
    "class_id",
    "modalias",
)


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    SESSION_MISMATCH = "session-mismatch"
    REPORT_DIGEST_MISMATCH = "report-digest-mismatch"
    ENVIRONMENT_MISMATCH = "environment-mismatch"
    TOPOLOGY_CHANGED = "topology-changed"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class ReportFreshness:
    """Metadata bound to the exact report bytes and its collection session."""

    report_sha256: str
    boot_session_sha256: str | None
    collected_monotonic_ns: int | None
    architecture: str | None
    kernel_release: str | None
    boot_mode: str | None
    topology_sha256: str | None


@dataclass(frozen=True)
class LiveSession:
    """Fresh observations collected immediately before plan confirmation."""

    boot_session_sha256: str | None
    monotonic_now_ns: int | None
    architecture: str | None
    kernel_release: str | None
    boot_mode: str | None
    topology_sha256: str | None


@dataclass(frozen=True)
class FreshnessDecision:
    status: FreshnessStatus
    freshness_gate_passed: bool
    reason: str
    age_seconds: float | None = None


def _is_digest(value: str | None) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def derive_boot_session_digest(boot_id: str) -> str:
    """Return a domain-separated digest; never return or persist the raw boot ID."""
    if not isinstance(boot_id, str) or not boot_id.strip():
        raise ValueError("boot_id must be a non-empty string")
    return hashlib.sha256(_BOOT_DOMAIN + boot_id.strip().encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> bytes:
    """Stable UTF-8 encoding used for report-local topology digests."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def topology_digest(devices: Iterable[Mapping[str, Any]]) -> str:
    """Hash only non-sensitive hardware topology facts, excluding local paths/serials."""
    normalized: list[dict[str, Any]] = []
    for device in devices:
        identity = device.get("identity") or {}
        item: dict[str, Any] = {
            "category": device.get("category"),
            "bus": device.get("bus"),
            "discovery_status": device.get("discovery_status"),
            "identity": {
                key: identity[key]
                for key in _TOPOLOGY_FIELDS
                if identity.get(key) is not None
            },
        }
        normalized.append(item)
    normalized.sort(key=canonical_json)
    return hashlib.sha256(canonical_json(normalized)).hexdigest()


def _decision(
    status: FreshnessStatus,
    reason: str,
    age_seconds: float | None = None,
) -> FreshnessDecision:
    return FreshnessDecision(
        status=status,
        freshness_gate_passed=status is FreshnessStatus.FRESH,
        reason=reason,
        age_seconds=age_seconds,
    )


def evaluate_freshness(
    report: ReportFreshness,
    live: LiveSession,
    *,
    expected_report_sha256: str,
    expected_boot_session_sha256: str,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> FreshnessDecision:
    """Fail closed unless report bytes, boot session, age, environment and topology match."""
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError("max_age_seconds must be a positive integer")

    if not _is_digest(report.report_sha256) or not _is_digest(expected_report_sha256):
        return _decision(FreshnessStatus.UNVERIFIABLE, "report digest is missing or malformed")
    if report.report_sha256 != expected_report_sha256:
        return _decision(
            FreshnessStatus.REPORT_DIGEST_MISMATCH,
            "report bytes differ from the report bound into the draft plan",
        )

    if not _is_digest(expected_boot_session_sha256):
        return _decision(FreshnessStatus.UNVERIFIABLE, "plan-bound boot-session identity is unavailable")
    if not _is_digest(report.boot_session_sha256) or not _is_digest(live.boot_session_sha256):
        return _decision(FreshnessStatus.UNVERIFIABLE, "boot-session identity is unavailable")
    if report.boot_session_sha256 != expected_boot_session_sha256:
        return _decision(
            FreshnessStatus.SESSION_MISMATCH,
            "source report boot session differs from the session bound into the draft plan",
        )
    if report.boot_session_sha256 != live.boot_session_sha256:
        return _decision(
            FreshnessStatus.SESSION_MISMATCH,
            "report was collected during a different boot session",
        )

    if (
        type(report.collected_monotonic_ns) is not int
        or type(live.monotonic_now_ns) is not int
        or report.collected_monotonic_ns < 0
        or live.monotonic_now_ns < 0
        or live.monotonic_now_ns < report.collected_monotonic_ns
    ):
        return _decision(
            FreshnessStatus.UNVERIFIABLE,
            "same-boot monotonic collection time is unavailable or inconsistent",
        )

    age_seconds = (live.monotonic_now_ns - report.collected_monotonic_ns) / 1_000_000_000
    if age_seconds > max_age_seconds:
        return _decision(
            FreshnessStatus.STALE,
            f"report age {age_seconds:.3f}s exceeds {max_age_seconds}s",
            age_seconds,
        )

    report_environment = (report.architecture, report.kernel_release, report.boot_mode)
    live_environment = (live.architecture, live.kernel_release, live.boot_mode)
    if any(not value for value in report_environment + live_environment):
        return _decision(
            FreshnessStatus.UNVERIFIABLE,
            "architecture, kernel release or boot mode is unavailable",
            age_seconds,
        )
    if report_environment != live_environment:
        return _decision(
            FreshnessStatus.ENVIRONMENT_MISMATCH,
            "live architecture, kernel release or boot mode changed",
            age_seconds,
        )

    if not _is_digest(report.topology_sha256) or not _is_digest(live.topology_sha256):
        return _decision(
            FreshnessStatus.UNVERIFIABLE,
            "hardware topology digest is unavailable",
            age_seconds,
        )
    if report.topology_sha256 != live.topology_sha256:
        return _decision(
            FreshnessStatus.TOPOLOGY_CHANGED,
            "revalidated device topology differs from the source report",
            age_seconds,
        )

    return _decision(
        FreshnessStatus.FRESH,
        "report bytes, boot session, age, environment and topology match",
        age_seconds,
    )
