# SPDX-License-Identifier: LicenseRef-Volnist
"""Compile and execute the native FPC classifier against small report fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pascal"
SOURCE = SOURCE_DIR / "wsm_classify.pas"


@unittest.skipUnless(shutil.which("fpc"), "FPC is absent; native classifier behaviour is not verified")
class FpcClassifierRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-classify-fpc-")
        cls.build_dir = Path(cls.temporary.name)
        cls.binary = cls.build_dir / "wsm-classify"
        command = [
            shutil.which("fpc") or "fpc",
            "-B", "-O2", "-Mobjfpc", "-Sh",
            f"-Fu{SOURCE_DIR}", f"-FU{cls.build_dir}", f"-FE{cls.build_dir}",
            f"-o{cls.binary}", str(SOURCE),
        ]
        built = subprocess.run(command, capture_output=True, text=True, check=False)
        if built.returncode != 0 or not cls.binary.is_file():
            raise AssertionError(
                "FPC failed to compile wsm_classify.pas\n"
                f"stdout:\n{built.stdout}\nstderr:\n{built.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def run_report(self, report: dict) -> dict:
        report_path = self.build_dir / "input.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result = subprocess.run(
            [str(self.binary), str(report_path)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_version_and_help(self) -> None:
        version = subprocess.run([str(self.binary), "--version"], capture_output=True, text=True)
        self.assertEqual(version.returncode, 0)
        self.assertEqual(version.stdout.strip(), "wsm-classify 0.2.0")
        help_result = subprocess.run([str(self.binary), "--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("REPORT.json", help_result.stdout)

    def test_bound_driver_is_known_but_never_certified(self) -> None:
        report = self.run_report({
            "devices": [{
                "device_id": "gpu-0",
                "category": "gpu",
                "discovery_status": "discovered",
                "driver": {"status": "bound", "bound_driver": "i915"},
                "functional_tests": [],
            }]
        })
        self.assertEqual(report["schema"], "wsm-hardware-classification/2")
        graphics = next(item for item in report["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["level"], "KNOWN")
        self.assertEqual(report["counts"]["CERTIFIED"], 0)

    def test_failed_functional_test_blocks_known(self) -> None:
        report = self.run_report({
            "devices": [{
                "device_id": "gpu-0",
                "category": "gpu",
                "discovery_status": "discovered",
                "driver": {"status": "bound", "bound_driver": "i915"},
                "functional_tests": [{"name": "display", "result": "failed"}],
            }]
        })
        graphics = next(item for item in report["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["level"], "UNKNOWN")

    def test_device_identifiers_are_json_escaped(self) -> None:
        identifier = 'gpu-"quoted"\\path'
        report = self.run_report({
            "devices": [{
                "device_id": identifier,
                "category": "gpu",
                "discovery_status": "discovered",
                "driver": {"status": "bound", "bound_driver": "i915"},
                "functional_tests": [],
            }]
        })
        graphics = next(item for item in report["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["evidence_states"], [identifier + "=driver-bound-not-tested"])

    def test_empty_device_list_is_diagnostic_only(self) -> None:
        report = self.run_report({"devices": []})
        self.assertEqual(report["counts"]["CERTIFIED"], 0)
        self.assertTrue(all(item["level"] == "UNKNOWN" for item in report["subsystems"]))

    def test_malformed_report_is_rejected(self) -> None:
        path = self.build_dir / "broken.json"
        path.write_text("{broken", encoding="utf-8")
        result = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
