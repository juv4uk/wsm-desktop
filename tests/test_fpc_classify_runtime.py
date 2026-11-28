# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime contract tests for the native Free Pascal subsystem classifier."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "pascal" / "wsm_classify.pas"


@unittest.skipUnless(shutil.which("fpc"), "FPC is installed in the dedicated native build workflow")
class FpcClassifierRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-classify-test-")
        cls.build_dir = Path(cls.temporary.name)
        cls.binary = cls.build_dir / "wsm-classify"
        result = subprocess.run(
            [
                shutil.which("fpc") or "fpc",
                "-B",
                "-O2",
                "-Mobjfpc",
                "-Sh",
                f"-FU{cls.build_dir}",
                f"-FE{cls.build_dir}",
                f"-o{cls.binary}",
                str(SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not cls.binary.is_file():
            raise AssertionError(
                f"FPC classifier build failed.\n{result.stdout}\n{result.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def classify(self, report: dict) -> dict:
        path = self.build_dir / "input.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        result = subprocess.run(
            [str(self.binary), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def report(device: dict) -> dict:
        return {"devices": [device]}

    def test_bound_driver_is_known_but_never_certified(self) -> None:
        result = self.classify(self.report({
            "device_id": 'pci-"quoted-id"',
            "category": "gpu",
            "discovery_status": "discovered",
            "driver": {"status": "bound", "bound_driver": "nvidia"},
            "functional_tests": [],
        }))
        graphics = next(item for item in result["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["level"], "KNOWN")
        self.assertIn('pci-"quoted-id"=driver-bound-not-tested', graphics["evidence_states"][0])
        self.assertEqual(result["counts"]["CERTIFIED"], 0)

    def test_failed_function_test_keeps_subsystem_unknown(self) -> None:
        result = self.classify(self.report({
            "device_id": "pci-0000:01:00.0",
            "category": "gpu",
            "discovery_status": "discovered",
            "driver": {"status": "bound", "bound_driver": "nouveau"},
            "functional_tests": [{"name": "display-output", "result": "failed"}],
        }))
        graphics = next(item for item in result["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["level"], "UNKNOWN")
        self.assertEqual(result["counts"]["CERTIFIED"], 0)

    def test_no_driver_record_does_not_become_known(self) -> None:
        result = self.classify(self.report({
            "device_id": "pci-0000:01:00.0",
            "category": "gpu",
            "discovery_status": "discovered",
            "driver": {"status": "unbound"},
            "functional_tests": [],
        }))
        graphics = next(item for item in result["subsystems"] if item["subsystem"] == "graphics")
        self.assertEqual(graphics["level"], "UNKNOWN")

    def test_cli_help_and_version(self) -> None:
        help_result = subprocess.run(
            [str(self.binary), "--help"], capture_output=True, text=True, check=False
        )
        version_result = subprocess.run(
            [str(self.binary), "--version"], capture_output=True, text=True, check=False
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertEqual(version_result.stdout.strip(), "wsm-classify 0.1.0")

    def test_malformed_json_is_rejected(self) -> None:
        path = self.build_dir / "broken.json"
        path.write_text("{broken", encoding="utf-8")
        result = subprocess.run(
            [str(self.binary), str(path)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 4)
        self.assertIn("not valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
