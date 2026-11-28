# SPDX-License-Identifier: LicenseRef-Volnist
"""Behaviour of the FPC/Python parity harness, not the state of the port.

The harness in scripts/check_fpc_parity.py is the only thing that decides
whether the Free Pascal collector agrees with the Python one. If it silently
passes on a disagreement, or silently skips a field, the whole port is
unverified while looking green. So these tests assert both directions:

* a report that differs in a compared field is reported, with the group, the
  field and both values named;
* a report that differs only in what the harness documents as not compared
  (the pci.ids labels and the bookkeeping) still passes.

None of this needs a Pascal compiler. It proves the comparison is red where it
must be red; it cannot prove the Pascal program produces the right values.
That is what .github/workflows/fpc-hwcheck-parity.yml is for.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_fpc_parity  # noqa: E402

SCRIPT = ROOT / "scripts" / "check_fpc_parity.py"


def report() -> dict:
    """A report shaped like the Python collector's, with all three groups."""
    return {
        "schema_version": "1.1.0",
        "report_id": "wsm-000000000000000000000000",
        "collected_at": "2026-11-28T08:07:36Z",
        "environment": {
            "architecture": "x86_64",
            "kernel_release": "6.12.0-test",
            "boot_mode": "uefi",
            "boot_mode_evidence": (
                "sysfs:/firmware/efi is present: the kernel was booted through EFI."
            ),
            "virtualization": "unknown",
            "platform": {
                "system_vendor": "Example Vendor",
                "bios_release": "5.12",
                "bios_date": "2021-01-15",
            },
        },
        "collectors": [{"name": "wsm-hwcheck-sysfs", "available": True,
                        "scope": "unprivileged-read-only"}],
        "devices": [
            {
                "device_id": "cpu-0",
                "category": "cpu",
                "bus": "cpu",
                "discovery_status": "discovered",
                "driver": {"status": "not-applicable"},
                "firmware": {"requirement": "unknown", "runtime_status": "unknown"},
                "functional_tests": [],
                "evidence": [],
            },
            {
                "device_id": "pci-0000:00:02.0",
                "category": "gpu",
                "bus": "pci",
                "discovery_status": "discovered",
                "driver": {
                    "status": "bound",
                    "bound_driver": "i915",
                    "module": "i915",
                    "module_loaded": True,
                },
                "firmware": {
                    "requirement": "unknown",
                    "runtime_status": "unknown",
                    "redistribution_status": "unknown",
                },
                "functional_tests": [],
                "evidence": [
                    {"kind": "live-observation", "source": "sysfs:/bus/pci/devices/0000:00:02.0",
                     "observed_at": "2026-11-28T08:07:36Z", "confidence": "confirmed",
                     "summary": "PCI function and its kernel driver binding were read from sysfs."}
                ],
                "identity": {
                    "local_path": "/bus/pci/devices/0000:00:02.0",
                    "vendor_id": "0x8086",
                    "device_id": "0x1912",
                    "class_id": "0x030000",
                    "modalias": "pci:v00008086d00001912",
                },
                "gpu": {
                    "boot_vga": True,
                    "drm_cards": ["card0"],
                    "pci_link": {
                        "current_speed": "8.0 GT/s PCIe",
                        "current_width": 16,
                        "max_speed": "8.0 GT/s PCIe",
                        "max_width": 16,
                    },
                },
            },
        ],
        "warnings": [],
        "limitations": [],
        "privacy": {
            "profile": "strict-local",
            "network_upload_performed": False,
            "network_requests_performed": False,
            "sensitive_identifiers_included": False,
        },
    }


def gpu_of(document: dict) -> dict:
    return next(item for item in document["devices"] if item["category"] == "gpu")


class ParityComparisonTests(unittest.TestCase):
    def test_identical_reports_agree(self) -> None:
        self.assertEqual(check_fpc_parity.compare(report(), report()), [])

    def test_boot_mode_disagreement_is_reported(self) -> None:
        other = report()
        other["environment"]["boot_mode"] = "bios"
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(
            any("boot_mode.boot_mode" in line for line in found), found
        )
        self.assertIn("'uefi'", found[0])
        self.assertIn("'bios'", found[0])

    def test_bios_date_disagreement_is_reported(self) -> None:
        other = report()
        other["environment"]["platform"]["bios_date"] = "2021-01-16"
        found = check_fpc_parity.compare(report(), other)
        self.assertEqual(len(found), 1, found)
        self.assertIn("bios.bios_date", found[0])

    def test_gpu_boot_vga_disagreement_is_reported(self) -> None:
        other = report()
        gpu_of(other)["gpu"]["boot_vga"] = False
        found = check_fpc_parity.compare(report(), other)
        self.assertEqual(len(found), 1, found)
        self.assertIn("gpu[0].gpu.boot_vga", found[0])

    def test_driver_binding_disagreement_is_reported(self) -> None:
        other = report()
        gpu_of(other)["driver"]["status"] = "none-known"
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(any("gpu[0].driver.status" in line for line in found), found)

    def test_unavailable_array_is_compared_in_order(self) -> None:
        """A fact listed as unavailable is a claim; dropping it is a difference."""
        left = report()
        right = report()
        gpu_of(left)["gpu"]["unavailable"] = ["boot_vga", "drm_cards"]
        gpu_of(right)["gpu"]["unavailable"] = ["drm_cards", "boot_vga"]
        found = check_fpc_parity.compare(left, right)
        self.assertTrue(found, "a reordered unavailable array must be a difference")

    def test_absent_key_is_a_difference_not_a_skip(self) -> None:
        other = report()
        del other["environment"]["boot_mode_evidence"]
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(
            any("<missing>" in line for line in found),
            f"an absent field must be compared, not skipped: {found}",
        )

    def test_absent_gpu_group_is_a_difference(self) -> None:
        other = report()
        del gpu_of(other)["gpu"]
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(found, "a missing gpu object must not pass as agreement")

    def test_missing_gpu_device_is_a_difference(self) -> None:
        other = report()
        other["devices"] = [d for d in other["devices"] if d["category"] != "gpu"]
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(any("length 1 != 0" in line for line in found), found)

    def test_pci_ids_names_are_not_compared(self) -> None:
        """pci.ids labels are outside the slice; the exclusion is deliberate."""
        other = report()
        gpu_of(other)["identity"]["manufacturer"] = "Intel Corporation"
        gpu_of(other)["identity"]["model"] = "HD Graphics 530"
        self.assertEqual(check_fpc_parity.compare(report(), other), [])

    def test_bookkeeping_is_not_compared(self) -> None:
        other = report()
        other["collected_at"] = "2026-11-28T09:00:00Z"
        other["report_id"] = "wsm-ffffffffffffffffffffffff"
        other["warnings"] = ["the FPC slice does not collect pci.ids names"]
        other["limitations"] = ["slice scope"]
        other["collectors"] = [{"name": "wsm-hwcheck-fpc-sysfs", "available": True,
                                "scope": "unprivileged-read-only"}]
        self.assertEqual(check_fpc_parity.compare(report(), other), [])

    def test_devices_outside_the_gpu_category_are_ignored(self) -> None:
        other = report()
        other["devices"][0]["driver"] = {"status": "bound", "bound_driver": "x"}
        self.assertEqual(check_fpc_parity.compare(report(), other), [])

    def test_an_unexpected_extra_field_is_a_difference(self) -> None:
        other = report()
        gpu_of(other)["gpu"]["ecc_supported"] = True
        found = check_fpc_parity.compare(report(), other)
        self.assertTrue(any("ecc_supported" in line for line in found), found)

    def test_mismatch_text_names_the_groups_and_the_exclusions(self) -> None:
        other = report()
        other["environment"]["boot_mode"] = "bios"
        found = check_fpc_parity.compare(report(), other)
        rendered = check_fpc_parity.render_mismatch(found, "py.json", "pas.json")
        self.assertIn("FPC-PARITY-FAIL", rendered)
        self.assertIn("boot_mode.boot_mode", rendered)
        self.assertIn("identity.manufacturer", rendered)


class FixtureTests(unittest.TestCase):
    """The fixtures must actually exercise the three groups."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.names = check_fpc_parity.emit_fixtures(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def collect(self, name: str) -> dict:
        sys.path.insert(0, str(ROOT))
        from wsm_hwcheck.collector import collect_report

        return collect_report(self.root / name / "sys", self.root / name / "proc")

    def test_three_trees_are_written(self) -> None:
        self.assertEqual(self.names, ["bios", "empty", "uefi"])
        for name in self.names:
            self.assertTrue((self.root / name / "sys").is_dir())
            self.assertTrue((self.root / name / "proc").is_dir())

    def test_the_fixtures_cover_all_three_boot_modes(self) -> None:
        modes = {name: self.collect(name)["environment"]["boot_mode"] for name in self.names}
        self.assertEqual(modes, {"uefi": "uefi", "bios": "bios", "empty": "unknown"})

    def test_the_uefi_fixture_populates_every_gpu_fact(self) -> None:
        gpu = gpu_of(self.collect("uefi"))["gpu"]
        self.assertIs(gpu["boot_vga"], True)
        self.assertEqual(gpu["drm_cards"], ["card0"])
        self.assertEqual(gpu["pci_link"]["current_width"], 16)
        self.assertNotIn("unavailable", gpu)

    def test_the_bios_fixture_leaves_every_gpu_fact_unavailable(self) -> None:
        gpu = gpu_of(self.collect("bios"))["gpu"]
        self.assertEqual(
            gpu["unavailable"],
            [
                "boot_vga",
                "drm_cards",
                "pci_link.current_speed",
                "pci_link.max_speed",
                "pci_link.current_width",
                "pci_link.max_width",
            ],
        )
        self.assertNotIn("boot_vga", gpu)

    def test_the_uefi_fixture_normalises_the_dmi_date(self) -> None:
        platform = self.collect("uefi")["environment"]["platform"]
        self.assertEqual(platform["bios_date"], "2021-01-15")
        self.assertEqual(platform["bios_release"], "5.12")

    def test_a_dmi_placeholder_is_not_a_bios_release(self) -> None:
        environment = self.collect("bios")["environment"]
        self.assertNotIn("bios_release", environment.get("platform", {}))
        self.assertNotIn("bios_date", environment.get("platform", {}))

    def test_each_fixture_agrees_with_itself_through_the_harness(self) -> None:
        for name in self.names:
            with self.subTest(fixture=name):
                self.assertEqual(
                    check_fpc_parity.compare(self.collect(name), self.collect(name)), []
                )


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.left = self.root / "python.json"
        self.right = self.root / "pascal.json"
        self.left.write_text(json.dumps(report()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_harness(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_agreement_exits_zero_and_says_so(self) -> None:
        self.right.write_text(json.dumps(report()), encoding="utf-8")
        completed = self.run_harness(str(self.left), str(self.right))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FPC-PARITY-PASS", completed.stdout)

    def test_disagreement_exits_one_with_a_named_diff(self) -> None:
        other = copy.deepcopy(report())
        gpu_of(other)["gpu"]["boot_vga"] = False
        self.right.write_text(json.dumps(other), encoding="utf-8")
        completed = self.run_harness(str(self.left), str(self.right))
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("FPC-PARITY-FAIL", completed.stderr)
        self.assertIn("gpu[0].gpu.boot_vga", completed.stderr)
        self.assertIn("True", completed.stderr)
        self.assertIn("False", completed.stderr)

    def test_unreadable_report_exits_two(self) -> None:
        self.right.write_text("{not json", encoding="utf-8")
        completed = self.run_harness(str(self.left), str(self.right))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("FPC-PARITY-ERROR", completed.stderr)

    def test_schema_mode_rejects_a_document_that_is_not_a_report(self) -> None:
        try:
            import jsonschema  # noqa: F401
        except ModuleNotFoundError:  # pragma: no cover - CI installs jsonschema
            self.skipTest("jsonschema is not installed")
        self.right.write_text(json.dumps({"devices": []}), encoding="utf-8")
        completed = self.run_harness(
            str(self.left), str(self.right),
            "--schema", str(ROOT / "schemas" / "hardware-report.schema.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("not schema-valid", completed.stderr)

    def test_emit_fixtures_writes_a_tree(self) -> None:
        target = self.root / "fixtures"
        completed = self.run_harness("--emit-fixtures", str(target))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((target / "uefi" / "sys" / "firmware" / "efi").is_dir())
        self.assertTrue(
            (target / "uefi" / "sys" / "bus/pci/devices/0000:00:02.0/boot_vga").is_file()
        )


if __name__ == "__main__":
    unittest.main()
