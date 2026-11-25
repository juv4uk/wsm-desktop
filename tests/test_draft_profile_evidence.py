# SPDX-License-Identifier: LicenseRef-Volnist
"""The drafter must produce a v2 bundle with hashed source bytes and no fake passes."""

from __future__ import annotations

import hashlib
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


def prepare_bundle(root: Path, report_value: dict | None = None):
    report_value = report_value or report()
    raw = json.dumps(report_value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    bundle = draft(report_value, "ASUS", "H170-PRO", "asus/h170-pro", raw)
    artifact = root / "artifacts" / "hardware-report.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(raw)
    return bundle, raw, artifact


class DraftTests(unittest.TestCase):
    def test_every_function_starts_not_assessed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _raw, _artifact = prepare_bundle(Path(temporary))
        self.assertTrue(bundle["verified_functions"])
        self.assertTrue(all(item["status"] == "not-assessed" for item in bundle["verified_functions"]))

    def test_draft_fails_validation_until_a_person_verifies_something(self) -> None:
        """The generator may create provenance, but it must never fabricate a pass."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _raw, _artifact = prepare_bundle(root)
            problems = validate(bundle, artifact_root=root)
        self.assertTrue(any("no function passed" in item for item in problems))

    def test_marking_one_function_pass_makes_a_complete_bundle_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _raw, _artifact = prepare_bundle(root)
            bundle["verified_functions"][0]["status"] = "pass"
            problems = validate(bundle, artifact_root=root)
        self.assertEqual(problems, [])

    def test_v2_artifact_hash_is_the_exact_source_report_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, raw, artifact = prepare_bundle(root)
            self.assertEqual(artifact.read_bytes(), raw)
            self.assertEqual(bundle["schema"], "wsm-profile-evidence/2")
            self.assertEqual(bundle["artifacts"][0]["path"], "artifacts/hardware-report.json")
            self.assertEqual(
                bundle["artifacts"][0]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(validate(bundle, artifact_root=root), ["no function passed: a bundle with only not-assessed entries is a hypothesis, not evidence"])

    def test_changed_source_report_bytes_invalidate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _raw, artifact = prepare_bundle(root)
            artifact.write_bytes(artifact.read_bytes() + b"tampered")
            problems = validate(bundle, artifact_root=root)
        self.assertTrue(any("does not match the bytes" in item for item in problems))

    def test_known_problems_become_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _raw, _artifact = prepare_bundle(Path(temporary))
        joined = " ".join(bundle["known_limitations"])
        self.assertIn("net-0", joined)
        self.assertIn("missing", joined)
        self.assertIn("network-link", joined)

    def test_pci_signature_is_lowercased_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _raw, _artifact = prepare_bundle(Path(temporary))
        self.assertEqual(bundle["hardware_signature"]["pci_ids"], ["10de:1c82"])

    def test_no_signature_means_no_signature_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _raw, _artifact = prepare_bundle(Path(temporary), report(devices=[]))
        self.assertNotIn("hardware_signature", bundle)

    def test_not_assessed_is_never_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _raw, _artifact = prepare_bundle(Path(temporary))
        self.assertTrue(bundle["not_assessed"])

    def test_report_without_id_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            draft({"devices": []}, "ASUS", "H170-PRO", "asus/h170-pro", b'{"devices": []}')


class CliTests(unittest.TestCase):
    def test_cli_writes_v2_evidence_and_exact_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            raw = json.dumps(report(), ensure_ascii=False).encode("utf-8")
            report_path.write_bytes(raw)
            profile_dir = directory / "asus" / "h170-pro"
            out = profile_dir / "evidence.json"
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
            artifact = profile_dir / "artifacts" / "hardware-report.json"
            self.assertEqual(written["schema"], "wsm-profile-evidence/2")
            self.assertEqual(artifact.read_bytes(), raw)
            self.assertEqual(
                written["artifacts"][0]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertTrue(all(item["status"] == "not-assessed" for item in written["verified_functions"]))
            self.assertTrue(any("no function passed" in item for item in validate(written, artifact_root=profile_dir)))

    def test_cli_refuses_to_overwrite_existing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            report_path.write_text(json.dumps(report()), encoding="utf-8")
            profile_dir = directory / "asus" / "h170-pro"
            artifact = profile_dir / "artifacts" / "hardware-report.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"keep existing evidence")
            out = profile_dir / "evidence.json"
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
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(artifact.read_bytes(), b"keep existing evidence")


if __name__ == "__main__":
    unittest.main()
