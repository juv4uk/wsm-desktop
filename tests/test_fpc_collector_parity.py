# SPDX-License-Identifier: LicenseRef-Volnist
"""Parity between the FPC collector slice and the Python collector.

The Pascal program is intentionally a partial identity/PCI slice, not a drop-in
replacement for the complete versioned Python report. This test compares every
field the slice claims to implement against the Python reference on the same host.
If FPC is absent locally, runtime checks skip explicitly; the pinned GitHub FPC
workflow installs the compiler and runs these checks without skipping.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "fpc" / "wsm_hwcheck.pas"
FPC_WORKFLOW = ROOT / ".github" / "workflows" / "fpc-build.yml"


class FpcCollectorParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fpc = shutil.which("fpc")
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def compile_slice(self) -> Path:
        """Build the slice and return its executable path."""
        self.assertIsNotNone(self.fpc, "FPC is required for this runtime test")
        output_dir = Path(self.temporary.name)
        completed = subprocess.run(
            [
                self.fpc,
                "-B",
                "-O2",
                "-Mobjfpc",
                "-Sh",
                f"-FU{output_dir}",
                f"-FE{output_dir}",
                f"-o{output_dir / 'wsm_hwcheck'}",
                str(SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"FPC failed to compile the collector.\nstdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}",
        )
        binary = output_dir / "wsm_hwcheck"
        self.assertTrue(binary.is_file(), "FPC reported success but emitted no executable")
        return binary

    def run_slice(self) -> dict:
        binary = self.compile_slice()
        completed = subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Pascal collector did not emit one valid JSON document: {exc}\n{completed.stdout}")
        self.assertEqual(payload["collector"], "wsm-hwcheck-pascal")
        self.assertIsInstance(payload.get("environment"), dict)
        self.assertIsInstance(payload.get("pci"), list)
        self.assertEqual(
            payload.get("evidence_level"),
            "read-only sysfs and uname; no MMIO, no module load, no write",
        )
        return payload

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; compiler/runtime parity is NOT proven")
    def test_the_slice_builds_and_emits_json(self) -> None:
        self.run_slice()

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; compiler/runtime parity is NOT proven")
    def test_environment_identity_matches_python_reference(self) -> None:
        sys.path.insert(0, str(ROOT))
        from wsm_hwcheck.collector import collect_report  # noqa: PLC0415

        python_report = collect_report(include_runtime_diagnostics=False)
        payload = self.run_slice()

        for field in ("architecture", "kernel_release"):
            self.assertEqual(
                payload["environment"].get(field),
                python_report["environment"].get(field),
                f"environment.{field} disagrees with the Python reference",
            )

    @unittest.skipUnless(shutil.which("fpc"), "fpc is not installed; compiler/runtime parity is NOT proven")
    def test_pci_identity_and_driver_binding_match_python_reference(self) -> None:
        """The GPU question depends on exact PCI identity and bound-driver evidence."""
        sys.path.insert(0, str(ROOT))
        from wsm_hwcheck.collector import collect_report  # noqa: PLC0415

        python_report = collect_report(include_runtime_diagnostics=False)
        python_pci = {
            device["device_id"]: device
            for device in python_report.get("devices", [])
            if device.get("bus") == "pci"
        }

        payload = self.run_slice()
        pascal_devices = payload["pci"]
        pascal_addresses = ["pci-" + device["address"] for device in pascal_devices]
        self.assertEqual(
            pascal_addresses,
            sorted(pascal_addresses),
            "Pascal PCI output must be stable and sorted by BDF",
        )
        pascal_pci = {"pci-" + device["address"]: device for device in pascal_devices}

        self.assertEqual(
            set(pascal_pci),
            set(python_pci),
            "the two collectors disagree about which PCI functions exist",
        )
        for device_id, pascal_device in pascal_pci.items():
            python_device = python_pci[device_id]
            identity = python_device.get("identity", {})
            self.assertEqual(pascal_device["vendor"], identity.get("vendor_id", ""))
            self.assertEqual(pascal_device["device"], identity.get("device_id", ""))
            self.assertEqual(pascal_device["class"], identity.get("class_id", ""))

            python_driver = python_device.get("driver", {})
            pascal_driver = pascal_device.get("driver", {})
            self.assertEqual(
                pascal_driver.get("status"),
                python_driver.get("status"),
                f"{device_id}: driver status disagrees",
            )
            self.assertEqual(
                pascal_driver.get("bound_driver"),
                python_driver.get("bound_driver"),
                f"{device_id}: bound driver disagrees",
            )
            self.assertEqual(
                pascal_driver.get("module"),
                python_driver.get("module"),
                f"{device_id}: driver module disagrees",
            )
            self.assertEqual(
                pascal_driver.get("module_loaded"),
                python_driver.get("module_loaded"),
                f"{device_id}: module-loaded evidence disagrees",
            )

    def test_the_source_discloses_that_it_was_not_compiled_in_its_authoring_environment(self) -> None:
        """The repository must not turn a skipped local check into a verified claim."""
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("У середовищі написання FPC не встановлено", text)

    def test_fpc_ci_compiles_pascal_programs_with_any_supported_source_extension(self) -> None:
        """Catch the silent .pas blind spot: FPC CI must find this program."""
        workflow = FPC_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git ls-files '*.lpr' '*.pas' '*.pp'", workflow)
        self.assertIn("grep -Eiq", workflow)
        self.assertIn("program|library", workflow)
        self.assertIn("python3 tests/test_fpc_collector_parity.py", workflow)


if __name__ == "__main__":
    unittest.main()
