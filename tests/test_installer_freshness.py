# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed consumer-side freshness policy tests; no producer schema changes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.freshness import (
    DEFAULT_MAX_AGE_SECONDS,
    FreshnessStatus,
    LiveSession,
    ReportFreshness,
    derive_boot_session_digest,
    evaluate_freshness,
    topology_digest,
)

REPORT_SHA = "a" * 64
TOPOLOGY_SHA = "b" * 64
BOOT_A = derive_boot_session_digest("boot-id-a")


def report(**overrides):
    values = {
        "report_sha256": REPORT_SHA,
        "boot_session_sha256": BOOT_A,
        "collected_monotonic_ns": 1_000_000_000,
        "architecture": "x86_64",
        "kernel_release": "6.8.0-test",
        "boot_mode": "uefi",
        "topology_sha256": TOPOLOGY_SHA,
    }
    values.update(overrides)
    return ReportFreshness(**values)


def live(**overrides):
    values = {
        "boot_session_sha256": BOOT_A,
        "monotonic_now_ns": 31_000_000_000,
        "architecture": "x86_64",
        "kernel_release": "6.8.0-test",
        "boot_mode": "uefi",
        "topology_sha256": TOPOLOGY_SHA,
    }
    values.update(overrides)
    return LiveSession(**values)


class InstallerFreshnessTests(unittest.TestCase):
    def decide(self, report_value=None, live_value=None, **kwargs):
        return evaluate_freshness(
            report_value or report(),
            live_value or live(),
            expected_report_sha256=REPORT_SHA,
            **kwargs,
        )

    def test_matching_report_is_confirmable(self):
        decision = self.decide()
        self.assertEqual(decision.status, FreshnessStatus.FRESH)
        self.assertTrue(decision.confirmable)
        self.assertEqual(decision.age_seconds, 30.0)

    def test_age_boundary_is_inclusive(self):
        decision = self.decide(
            live_value=live(monotonic_now_ns=1_000_000_000 + DEFAULT_MAX_AGE_SECONDS * 1_000_000_000)
        )
        self.assertEqual(decision.status, FreshnessStatus.FRESH)

    def test_stale_report_is_not_confirmable(self):
        decision = self.decide(
            live_value=live(monotonic_now_ns=1_000_000_000 + (DEFAULT_MAX_AGE_SECONDS + 1) * 1_000_000_000)
        )
        self.assertEqual(decision.status, FreshnessStatus.STALE)
        self.assertFalse(decision.confirmable)

    def test_previous_boot_report_is_rejected(self):
        decision = self.decide(report_value=report(boot_session_sha256=derive_boot_session_digest("old-boot")))
        self.assertEqual(decision.status, FreshnessStatus.SESSION_MISMATCH)
        self.assertFalse(decision.confirmable)

    def test_missing_boot_identity_is_unverifiable(self):
        decision = self.decide(report_value=report(boot_session_sha256=None))
        self.assertEqual(decision.status, FreshnessStatus.UNVERIFIABLE)
        self.assertFalse(decision.confirmable)

    def test_missing_monotonic_time_is_unverifiable(self):
        decision = self.decide(live_value=live(monotonic_now_ns=None))
        self.assertEqual(decision.status, FreshnessStatus.UNVERIFIABLE)
        self.assertFalse(decision.confirmable)

    def test_monotonic_clock_regression_is_unverifiable(self):
        decision = self.decide(live_value=live(monotonic_now_ns=999_999_999))
        self.assertEqual(decision.status, FreshnessStatus.UNVERIFIABLE)
        self.assertFalse(decision.confirmable)

    def test_plan_report_digest_mismatch_is_rejected(self):
        decision = evaluate_freshness(
            report(),
            live(),
            expected_report_sha256="c" * 64,
        )
        self.assertEqual(decision.status, FreshnessStatus.REPORT_DIGEST_MISMATCH)
        self.assertFalse(decision.confirmable)

    def test_architecture_kernel_or_boot_mode_change_is_rejected(self):
        for field, value in (
            ("architecture", "aarch64"),
            ("kernel_release", "6.9.0-test"),
            ("boot_mode", "bios"),
        ):
            with self.subTest(field=field):
                decision = self.decide(live_value=live(**{field: value}))
                self.assertEqual(decision.status, FreshnessStatus.ENVIRONMENT_MISMATCH)
                self.assertFalse(decision.confirmable)

    def test_missing_environment_is_unverifiable(self):
        decision = self.decide(live_value=live(kernel_release=None))
        self.assertEqual(decision.status, FreshnessStatus.UNVERIFIABLE)
        self.assertFalse(decision.confirmable)

    def test_topology_change_is_rejected(self):
        decision = self.decide(live_value=live(topology_sha256="d" * 64))
        self.assertEqual(decision.status, FreshnessStatus.TOPOLOGY_CHANGED)
        self.assertFalse(decision.confirmable)

    def test_missing_topology_digest_is_unverifiable(self):
        decision = self.decide(live_value=live(topology_sha256=None))
        self.assertEqual(decision.status, FreshnessStatus.UNVERIFIABLE)
        self.assertFalse(decision.confirmable)

    def test_boot_digest_is_domain_separated_and_deterministic(self):
        self.assertEqual(BOOT_A, derive_boot_session_digest("boot-id-a"))
        self.assertNotEqual(BOOT_A, derive_boot_session_digest("boot-id-b"))
        self.assertNotIn("boot-id-a", BOOT_A)

    def test_topology_digest_ignores_sensitive_local_path_and_is_order_independent(self):
        first = [
            {
                "category": "gpu",
                "bus": "pci",
                "discovery_status": "discovered",
                "identity": {"vendor_id": "0x10de", "device_id": "0x1c82", "local_path": "/sys/devices/secret"},
            },
            {
                "category": "network",
                "bus": "pci",
                "discovery_status": "discovered",
                "identity": {"vendor_id": "0x8086", "device_id": "0x15b8"},
            },
        ]
        second = list(reversed(first))
        self.assertEqual(topology_digest(first), topology_digest(second))
        changed = [dict(first[0]), dict(first[1], identity={"vendor_id": "0x8086", "device_id": "0x9999"})]
        self.assertNotEqual(topology_digest(first), topology_digest(changed))

    def test_invalid_max_age_is_rejected(self):
        with self.assertRaises(ValueError):
            self.decide(max_age_seconds=0)


if __name__ == "__main__":
    unittest.main()
