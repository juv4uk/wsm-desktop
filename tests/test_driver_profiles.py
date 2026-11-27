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
LOCKED_NONGUIX_COMMIT = "6b8897cd6f3223b158c070cdc9cc638279f8c337"
OWNER_PROFILE = "https://github.com/juv4uk/wsm-os/blob/40ef00079d478d43fa496ec066bb96ac4c0850a3/docs/OWNER-HARDWARE-PROFILE.md"


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

    def test_manifest_schema_version_is_explicit_and_current(self) -> None:
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], "1.2.0")
        self.assertEqual(self.free["schema_version"], "1.2.0")
        self.assertEqual(self.compat["schema_version"], "1.2.0")
        notes = self.schema["$defs"]["candidate"]["properties"]["notes"]
        self.assertEqual(notes["type"], "array")
        self.assertEqual(notes["items"]["type"], "string")

    def test_free_and_compatibility_profiles_reference_separate_complete_locks(self) -> None:
        free_lock = (ROOT / "channels.lock.scm").read_text(encoding="utf-8")
        compatibility_lock = (ROOT / "channels" / "compatibility.lock.scm").read_text(encoding="utf-8")

        self.assertEqual(self.free["source"]["channel_lock_file"], "channels.lock.scm")
        self.assertEqual(
            self.free["source"]["channel_revisions"],
            [{"name": "guix", "url": "https://git.guix.gnu.org/guix.git", "commit": LOCKED_GUIX_COMMIT}],
        )
        self.assertIn(f'(commit "{LOCKED_GUIX_COMMIT}")', free_lock)
        self.assertIn("Authenticated Guix channel lock", free_lock)
        self.assertNotIn("(name 'nonguix)", free_lock)
        self.assertEqual(
            self.free["source"]["channel_authentication_evidence"],
            "authenticated-pull-recorded-build-not-evaluated",
        )

        self.assertEqual(
            self.compat["source"]["channel_lock_file"],
            "channels/compatibility.lock.scm",
        )
        self.assertEqual(
            self.compat["source"]["channel_revisions"],
            [
                {"name": "guix", "url": "https://git.guix.gnu.org/guix.git", "commit": LOCKED_GUIX_COMMIT},
                {"name": "nonguix", "url": "https://gitlab.com/nonguix/nonguix", "commit": LOCKED_NONGUIX_COMMIT},
            ],
        )
        self.assertIn(f'(commit "{LOCKED_GUIX_COMMIT}")', compatibility_lock)
        self.assertIn(f'(commit "{LOCKED_NONGUIX_COMMIT}")', compatibility_lock)
        self.assertIn("(name 'nonguix)", compatibility_lock)
        self.assertEqual(self.compat["source"]["channel_authentication_evidence"], "not-evaluated")


    def test_profiles_are_explicitly_draft_and_not_build_evidence(self) -> None:
        for profile in (self.free, self.compat):
            with self.subTest(profile=profile["profile_id"]):
                self.assertEqual(profile["profile_status"], "draft")
                self.assertIsNone(profile["source"]["source_commit"])
                self.assertIn(profile["source"]["channel_lock_file"], {"channels.lock.scm", "channels/compatibility.lock.scm"})
                self.assertTrue(profile["source"]["channel_revisions"])
                if profile["profile_class"] == "free":
                    self.assertEqual(profile["source"]["channel_authentication_evidence"], "authenticated-pull-recorded-build-not-evaluated")
                else:
                    self.assertEqual(profile["source"]["channel_authentication_evidence"], "not-evaluated")

    def test_free_profile_excludes_nonfree_and_only_claims_evidence_backed_functions(self) -> None:
        self.assertEqual(self.free["profile_class"], "free")
        self.assertTrue(self.free["enabled_by_default"])
        self.assertFalse(self.free["policy"]["nonfree_components_included"])
        docs = (ROOT / "docs" / "drivers" / "PROFILES.md").read_text(encoding="utf-8")
        self.assertIn("enabled_by_default: true", docs)
        self.assertIn("не підтверджують Free-сумісність кожного пакета", docs)
        for item in self.free["devices"]:
            with self.subTest(device=item["device_id"]):
                if item["device_id"] == "intel-mei-heci":
                    self.assertEqual(item["functional_validation"]["status"], "passed")
                    self.assertEqual(item["functional_validation"]["environment"], "physical-linux")
                    self.assertEqual(item["pci_ids"], ["8086:a13a"])
                    self.assertEqual(len(item["identity_evidence"]), 1)
                    self.assertTrue(any(e["kind"] == "functional-test" for e in item["functional_validation"]["evidence"]))
                else:
                    self.assertEqual(item["functional_validation"]["status"], "not-run")
                    self.assertEqual(item["functional_validation"]["environment"], "none")
                    if item["device_id"] == "nvidia-gtx-1050-ti":
                        self.assertEqual(item["pci_ids"], ["10de:1c82"])
                        self.assertEqual(len(item["identity_evidence"]), 1)
                    else:
                        self.assertEqual(item["pci_ids"], [])
                        self.assertEqual(item["identity_evidence"], [])
                firmware = item["firmware"]
                self.assertIn(firmware["redistribution"], {"free", "nonfree", "mixed", "unknown", "not-applicable"})
                if firmware["redistribution"] in {"nonfree", "mixed"}:
                    # A known nonfree requirement may be documented without being shipped.
                    self.assertEqual(firmware["package_candidates"], [])
                    self.assertEqual(firmware["package_resolution"], "not-assessed")
                    self.assertEqual(firmware["live_rootfs"], "not-assessed")
                    self.assertEqual(firmware["initrd"], "not-assessed")
                    self.assertEqual(firmware["installed_rootfs"], "not-assessed")
                    self.assertEqual(firmware["runtime_load"], "not-assessed")
                for candidate in item["driver_candidates"]:
                    self.assertEqual(candidate["package_resolution"], "not-assessed")
                    if item["device_id"] == "nvidia-gtx-1050-ti" and candidate["candidate_id"] == "nouveau-pascal":
                        self.assertEqual(candidate["runtime_binding"], "bound")
                        self.assertTrue(any(e["kind"] == "functional-test" for e in candidate["evidence"]))
                    else:
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

    def test_only_evidence_backed_pci_ids_are_populated(self) -> None:
        for profile in (self.free, self.compat):
            for item in profile["devices"]:
                with self.subTest(profile=profile["profile_id"], device=item["device_id"]):
                    if "nvidia-gtx-1050-ti" in item["device_id"]:
                        self.assertEqual(item["pci_ids"], ["10de:1c82"])
                        self.assertEqual(len(item["identity_evidence"]), 1)
                        self.assertIn("VEN_10DE DEV_1C82", item["identity_evidence"][0]["summary"])
                    elif item["device_id"] == "intel-mei-heci" and profile["profile_id"] == "h170-free":
                        self.assertEqual(item["pci_ids"], ["8086:a13a"])
                        self.assertEqual(len(item["identity_evidence"]), 1)
                        self.assertIn("8086:a13a", item["identity_evidence"][0]["summary"])
                    else:
                        self.assertEqual(item["pci_ids"], [])
                        self.assertEqual(item["identity_evidence"], [])
        gpu = next(item for item in self.free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        self.assertEqual(gpu["observed_bdf"], "00000000:01:00.0")
        self.assertTrue(any("BDF" in note or "bus address" in note for note in gpu["notes"]))


    def test_pascal_external_runtime_evidence_does_not_validate_free_profile(self) -> None:
        free_gpu = next(item for item in self.free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        nvk = next(item for item in free_gpu["driver_candidates"] if item["candidate_id"] == "nouveau-pascal")
        self.assertTrue(any(
            item["kind"] == "upstream-reference"
            and item.get("source_url") == "https://docs.mesa3d.org/drivers/nvk.html"
            for item in nvk["evidence"]
        ))
        self.assertEqual(nvk["package_resolution"], "not-assessed")
        self.assertEqual(nvk["runtime_binding"], "bound")
        self.assertTrue(any(item["kind"] == "functional-test" and "Kali Linux 7.2.15" in item["summary"] for item in nvk["evidence"]))
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
        latest_580_evidence = next(
            item for item in nvidia["evidence"]
            if item.get("source_url") == "https://www.nvidia.com/en-us/drivers/details/285683/"
        )
        self.assertIn("GeForce GTX 1050 Ti", latest_580_evidence["summary"])
        self.assertIn("580.196.11", latest_580_evidence["source"])
        self.assertIn("does not prove", latest_580_evidence["summary"])

        exact_device_evidence = next(
            item for item in nvidia["evidence"]
            if item.get("source_url") == "https://download.nvidia.com/XFree86/Linux-x86_64/580.126.09/README/supportedchips.html"
        )
        self.assertIn("1C82", exact_device_evidence["summary"])
        self.assertIn("does not prove", exact_device_evidence["summary"])
        self.assertEqual(nvidia["package_resolution"], "not-assessed")
        self.assertEqual(nvidia["source_license"], "unknown")
        self.assertEqual(compat_gpu["functional_validation"]["status"], "not-run")

    def test_pinned_linux_libre_kernel_config_exposes_h170_drivers(self) -> None:
        self.assertEqual(self.free["kernel"]["version"], "7.3.5")
        self.assertEqual(self.free["kernel"]["configuration_status"], "available")
        expected = {
            "intel-hd-530": ("i915-mesa", "module-available"),
            "nvidia-gtx-1050-ti": ("nouveau-pascal", "module-available"),
            "killer-e2200": ("alx-e2200", "module-available"),
            "kingston-nv2": ("nvme-controller", "built-in"),
            "samsung-sata": ("ahci-controller", "module-available"),
            "hda-audio": ("snd-hda-intel", "module-available"),
        }
        for device_id, (candidate_id, status) in expected.items():
            device = next(item for item in self.free["devices"] if item["device_id"] == device_id)
            candidate = next(item for item in device["driver_candidates"] if item["candidate_id"] == candidate_id)
            self.assertEqual(candidate["kernel_config"], status)
            self.assertTrue(any(item["source"] == "Pinned Guix Linux-libre 7.3 x86_64 default kernel configuration" for item in candidate["evidence"]))
            self.assertEqual(candidate["package_resolution"], "not-assessed")
            self.assertEqual(candidate["runtime_binding"], "bound" if device_id == "nvidia-gtx-1050-ti" else "unknown")

    def test_guix_enables_nvk_but_profile_does_not_claim_runtime_support(self) -> None:
        gpu = next(item for item in self.free["devices"] if item["device_id"] == "nvidia-gtx-1050-ti")
        candidate = next(item for item in gpu["driver_candidates"] if item["candidate_id"] == "nouveau-pascal")
        self.assertTrue(any(item["source"] == "Pinned GNU Guix Mesa/Linux-libre package definitions" for item in candidate["evidence"]))
        self.assertEqual(candidate["package_resolution"], "not-assessed")
        self.assertEqual(candidate["runtime_binding"], "bound")
        self.assertTrue(any(item["kind"] == "functional-test" for item in candidate["evidence"]))
        self.assertEqual(gpu["functional_validation"]["status"], "not-run")
        self.assertEqual(gpu["firmware"]["requirement"], "required")
        self.assertEqual(gpu["firmware"]["redistribution"], "nonfree")

    def test_intel_mei_heci_is_separate_from_pre_os_csme_firmware(self) -> None:
        mei = next(item for item in self.free["devices"] if item["device_id"] == "intel-mei-heci")
        self.assertEqual(mei["pci_ids"], ["8086:a13a"])
        candidate = next(item for item in mei["driver_candidates"] if item["candidate_id"] == "mei-me")
        self.assertEqual(candidate["kernel_module"], "mei_me")
        self.assertEqual(candidate["kernel_config"], "module-available")
        self.assertEqual(candidate["runtime_binding"], "unknown")
        self.assertEqual(mei["firmware"]["requirement"], "not-required")
        self.assertEqual(mei["functional_validation"]["status"], "passed")
        self.assertEqual(mei["functional_validation"]["environment"], "physical-linux")
        self.assertTrue(any(e["source"] == "wsm-os HECI hardware trace (bare-metal Kali Linux)" for e in mei["functional_validation"]["evidence"]))

    def test_cpu_microcode_is_documented_but_not_shipped_in_free_profile(self) -> None:
        cpu = next(item for item in self.free["devices"] if item["device_id"] == "skylake-i5-6400")
        firmware = cpu["firmware"]
        self.assertEqual(firmware["requirement"], "optional")
        self.assertEqual(firmware["redistribution"], "nonfree")
        self.assertEqual(firmware["package_candidates"], [])
        self.assertEqual(firmware["package_resolution"], "not-assessed")
        self.assertEqual(firmware["initrd"], "not-assessed")
        self.assertEqual(firmware["runtime_load"], "not-assessed")
        self.assertTrue(any("Intel official Linux processor microcode repository license" == e["source"] for e in firmware["evidence"]))

    def test_host_drivers_without_external_firmware_are_classified_explicitly(self) -> None:
        for device_id in ("killer-e2200", "hda-audio", "kingston-nv2", "samsung-sata"):
            device = next(item for item in self.free["devices"] if item["device_id"] == device_id)
            self.assertEqual(device["firmware"]["requirement"], "not-required")
            self.assertEqual(device["firmware"]["redistribution"], "not-applicable")
            self.assertTrue(any(item["kind"] == "upstream-reference" for item in device["firmware"]["evidence"]))
            self.assertEqual(device["firmware"]["package_resolution"], "not-assessed")
            self.assertEqual(device["functional_validation"]["status"], "not-run")

    def test_wifi_and_bluetooth_remain_unobserved(self) -> None:
        for profile in (self.free, self.compat):
            self.assertIn("wifi", profile["unobserved_device_classes"])
            self.assertIn("bluetooth", profile["unobserved_device_classes"])

    def test_owner_profile_is_an_immutable_uefi_inventory_source(self) -> None:
        for profile in (self.free, self.compat):
            self.assertEqual(profile["target"]["evidence_source"], OWNER_PROFILE)
            self.assertEqual(profile["target"]["evidence_date"], "2026-09-02")
            self.assertEqual(profile["target"]["firmware_version"], "F22e")
            self.assertEqual(profile["target"]["boot_mode"], "uefi")
            self.assertEqual(profile["target"]["secure_boot"], "unknown")
            self.assertFalse(profile["policy"]["automatic_firmware_updates"])
            self.assertFalse(profile["policy"]["host_disk_writes"])


if __name__ == "__main__":
    unittest.main()
