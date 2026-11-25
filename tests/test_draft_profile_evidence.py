# SPDX-License-Identifier: LicenseRef-Volnist
"""The drafter must produce a skeleton that is honest by construction."""

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
sys.path.insert(0, str(ROOT))

from draft_profile_evidence import draft, pci_ids_from, problems_from  # noqa: E402
from wsm_install.profile import problems as validate  # noqa: E402


def report(**overrides) -> dict:
    base = {
        "schema_version": "1.0.0",
        "report_id": "0f3c9a1e-2b44-4c8d-9f10-77a1b2c3d4e5",
        "collected_at": "2026-11-26T10:00:00Z",
        "devices": [
            {
                "device_id": "gpu-0",
                "category": "gpu",
                "discovery_status": "detected",
                "identity": {"pci_id": "10DE:1C82"},
                "firmware": {"requirement": "required", "runtime_status": "loaded"},
                "functional_tests": [],
            },
            {
                "device_id": "net-0",
                "category": "network",
                "discovery_status": "unknown",
                "identity": {},
                "firmware": {"requirement": "required", "runtime_status": "missing"},
                "functional_tests": [{"capability": "network-link", "status": "failed"}],
            },
        ],
        "warnings": [],
    }
    base.update(overrides)
    return base


class DraftTests(unittest.TestCase):
    def test_every_function_starts_not_assessed(self) -> None:
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        self.assertTrue(bundle["verified_functions"])
        self.assertTrue(all(f["status"] == "not-assessed" for f in bundle["verified_functions"]))

    def test_draft_fails_validation_until_a_person_verifies_something(self) -> None:
        """This is the whole point: the generator cannot produce a passing bundle."""
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        self.assertTrue(validate(bundle))

    def test_marking_one_function_pass_makes_it_valid(self) -> None:
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        bundle["verified_functions"][0]["status"] = "pass"
        # The report's own problems must still be listed as limitations.
        self.assertEqual(validate(bundle), [])

    def test_known_problems_become_limitations(self) -> None:
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        joined = " ".join(bundle["known_limitations"])
        self.assertIn("net-0", joined)
        self.assertIn("missing", joined)
        self.assertIn("network-link", joined)

    def test_pci_signature_is_lowercased_and_deduplicated(self) -> None:
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        self.assertEqual(bundle["hardware_signature"]["pci_ids"], ["10de:1c82"])

    def test_no_signature_means_no_signature_key(self) -> None:
        empty = report(devices=[])
        bundle = draft(empty, "ASUS", "H170-PRO", "asus/h170-pro")
        self.assertNotIn("hardware_signature", bundle)

    def test_not_assessed_is_never_empty(self) -> None:
        bundle = draft(report(), "ASUS", "H170-PRO", "asus/h170-pro")
        self.assertTrue(bundle["not_assessed"])

    def test_report_without_id_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            draft({"devices": []}, "ASUS", "H170-PRO", "asus/h170-pro")


class CliTests(unittest.TestCase):
    def test_cli_writes_a_file_and_says_it_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            report_path.write_text(json.dumps(report()), encoding="utf-8")
            out = directory / "evidence.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "draft_profile_evidence.py"),
                    "--report", str(report_path),
                    "--vendor", "ASUS",
                    "--model", "H170-PRO",
                    "--slug", "asus/h170-pro",
                    "--out", str(out),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("not-assessed", completed.stderr)
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(written["schema"], "wsm-profile-evidence/1")


if __name__ == "__main__":
    unittest.main()
