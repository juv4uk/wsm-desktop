# SPDX-License-Identifier: LicenseRef-Volnist
"""Validation tests for staged H170 driver/firmware profile manifests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "drivers" / "schema" / "profile.schema.json"
PROFILE_DIR = ROOT / "drivers" / "profiles"
LOCKED_GUIX_COMMIT = "4e5195be20d9b124df8a8bb69213412236e4668e"
OWNER_PROFILE = "https://github.com/juv4uk/wsm-os/blob/main/docs/OWNER-HARDWARE-PROFILE.md"


class DriverProfileManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )
        cls.free = json.loads((PROFILE_DIR / "h170-free.json").read_text(encoding="utf-8"))
        cls.compat = json.loads((PROFILE_DIR / "h170-compatibility.json").read_text(encoding="utf-8"))

    def assertValidProfile(self, profile: dict) -> None:
        errors = sorted(
            self.validator.iter_errors(profile),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(
            errors,
            [],
            "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors),
        )

    def test_both_profiles_validate_against_draft_2020_12(self) -> None:
        self.assertValidProfile(self.free)
        self.assertValidProfile(self.compat)

    def test_channel_commit_matches_the_current_authenticated_free_lock(self) -> None:
        lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        self.assertIn(f'(commit "{LOCKED_GUIX_COMMIT}")', lock)
        self.assertIn("Authenticated Guix channel lock", lock)
        # The lock establishes input identity, not package resolution/build.
        for profile in (self.free, self.compat):
            self.assertEqual(profile["source"]["channel_commit"], LOCKED_GUIX_COMMIT)
            self.assertEqual(
                profile["source"]["channel_authentication_evidence"],
                "authenticated-pull-recorded-build-not-evaluated",
            )

    def test_profiles_are_explicitly_draft_and_not_build_evidence(self) -> None:
        for profile in (self.free, self.compat):
            with self.subTest(profile=profile["profile_id"]):
                self.assertEqual(profile["profile_status"], "draft")
                self.assertIsNone(profile["source"]["source_commit"])
                self.assertEqual(profile["source"]["channel_commit"], LOCKED_GUIX_COMMIT)
                self.assertEqual(
                    profile["source"]["channel_authentication_evidence"],
                    "authenticated-pull-recorded-build-not-evaluated",
                )

    def test_free_profile_never_claims_nonfree_or_functional_support(self) -> None:
        self.assertEqual(self.free["profile_class"], "free")
        self.assertTrue(self.free["enabled_by_default"])
        self.assertFalse(self.free["policy"]["nonfree_components_included"])
        docs = (ROOT / "docs" / "drivers" / "PROFILES.md").read_text(encoding="utf-8")
        self.assertIn("enabled_by_default: true", docs)
        self.assertIn("не підтверджують Free-сумісність кожного пакета", docs)
        for item in self.free["devices"]:
            with self.subTest(device=item["device_id"]):
                self.assertEqual(item["functional_validation"]["status"], "not-run")
                self.assertEqual(item["functional_validation"]["environment"], "none")
                if item["device_id"] == "nvidia-gtx-1050-ti":
                    self.assertEqual(item["pci_ids"], ["10de:1c82"])
                    self.assertEqual(len(item["identity_evidence"]), 1)
                else:
                    self.assertEqual(item["pci_ids"], [])
                    self.assertEqual(item["identity_evidence"], [])
                self.assertEqual(item["firmware"]["redistribution"], "unknown")
                for candidate in item["driver_candidates"]:
                    self.assertEqual(candidate["package_resolution"], "not-assessed")
                    self.assertEqual(candidate["runtime_binding"], "unknown")
                    self.assertEqual(candidate["source_license"], "unknown")

    def test_compatibility_profile_is_opt_in_and_does_not_claim_distribution_rights(self) -> None:
        self.assertEqual(self.compat["profile_class"], "compatibility")
        self.assertFalse(self.compat["enabled_by_default"])
        self.assertEqual(self.compat["base_profile"], "h170-free")
        self.assertFalse(self.compat["policy"]["nonfree_components_included"])
        candidate = self.compat["devices"][0]["driver_candidates"][0]
        self.assertEqual(candidate["candidate_id"], "nvidia-linux-580")
        self.assertEqual(candidate["package_resolution"], "not-assessed")
        self.assertEqual(candidate["package_candidates"], [])
        self.assertEqual(candidate["source_license"], "unknown")
        self.assertEqual(self.compat["devices"][0]["functional_validation"]["status"], "not-run")

    def test_only_windows_observed_nvidia_id_is_populated(self) -> None:
        for profile in (self.free, self.compat):
            for item in profile["devices"]:
                with self.subTest(profile=profile["profile_id"], device=item["device_id"]):
                    if "nvidia-gtx-1050-ti" in item["device_id"]:
                        self.assertEqual(item["pci_ids"], ["10de:1c82"])
                        self.assertEqual(len(item["identity_evidence"]), 1)
                        self.assertIn("VEN_10DE DEV_1C82", item["identity_evidence"][0]["summary"])
                    else:
                        self.assertEqual(item["pci_ids"], [])
                        self.assertEqual(item["identity_evidence"], [])
        gpu = next(item for item in self.free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        self.assertEqual(gpu["observed_bdf"], "00000000:01:00.0")
        self.assertTrue(any("BDF" in note or "bus address" in note for note in gpu["notes"]))


    def test_pascal_upstream_driver_evidence_keeps_runtime_status_unverified(self) -> None:
        free_gpu = next(item for item in self.free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        nvk = next(item for item in free_gpu["driver_candidates"] if item["candidate_id"] == "nouveau-pascal")
        self.assertTrue(any(
            item["kind"] == "upstream-reference"
            and item.get("source_url") == "https://docs.mesa3d.org/drivers/nvk.html"
            for item in nvk["evidence"]
        ))
        self.assertEqual(nvk["package_resolution"], "not-assessed")
        self.assertEqual(nvk["runtime_binding"], "unknown")
        self.assertEqual(free_gpu["functional_validation"]["status"], "not-run")

        compat_gpu = next(item for item in self.compat["devices"] if item["device_id"] == "nvidia-gtx-1050-ti-compat")
        nvidia = next(item for item in compat_gpu["driver_candidates"] if item["candidate_id"] == "nvidia-linux-580")
        urls = {item.get("source_url") for item in nvidia["evidence"]}
        self.assertIn(
            "https://nvidia.custhelp.com/app/answers/detail/a_id/3142/kw/windows%20supported/related/1",
            urls,
        )
        self.assertIn(
            "https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/610/kernel-modules.html",
            urls,
        )
        self.assertEqual(nvidia["package_resolution"], "not-assessed")
        self.assertEqual(nvidia["source_license"], "unknown")
        self.assertEqual(compat_gpu["functional_validation"]["status"], "not-run")

    def test_wifi_and_bluetooth_remain_unobserved(self) -> None:
        for profile in (self.free, self.compat):
            self.assertIn("wifi", profile["unobserved_device_classes"])
            self.assertIn("bluetooth", profile["unobserved_device_classes"])

    def test_owner_profile_is_the_physical_inventory_source(self) -> None:
        self.assertEqual(self.free["target"]["evidence_source"], OWNER_PROFILE)
        self.assertEqual(self.compat["target"]["evidence_source"], OWNER_PROFILE)
        for profile in (self.free, self.compat):
            self.assertFalse(profile["policy"]["automatic_firmware_updates"])
            self.assertFalse(profile["policy"]["host_disk_writes"])


if __name__ == "__main__":
    unittest.main()
