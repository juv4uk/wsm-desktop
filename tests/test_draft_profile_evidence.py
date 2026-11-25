# SPDX-License-Identifier: LicenseRef-Volnist
"""The v2 evidence drafter must preserve source bytes without claiming functionality."""

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

from draft_profile_evidence import REPORT_ARTIFACT, draft, pci_ids_from, problems_from  # noqa: E402
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


PROFILE_SOURCE_BYTES = b";; synthetic profile source\n"


def make_draft(root: Path, source_report: dict | None = None) -> tuple[dict, bytes]:
    source_report = report() if source_report is None else source_report
    raw = json.dumps(source_report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    root.mkdir(parents=True, exist_ok=True)
    profile_path = root / "profile.scm"
    profile_path.write_bytes(PROFILE_SOURCE_BYTES)
    bundle = draft(source_report, "ASUS", "H170-PRO", "asus/h170-pro", raw, PROFILE_SOURCE_BYTES)
    artifact = root / REPORT_ARTIFACT
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(raw)
    return bundle, raw


class DraftTests(unittest.TestCase):
    def test_every_function_starts_not_assessed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = make_draft(Path(temporary))
        self.assertEqual(bundle["schema"], "wsm-profile-evidence/2")
        self.assertTrue(bundle["verified_functions"])
        self.assertTrue(all(f["status"] == "not-assessed" for f in bundle["verified_functions"]))

    def test_draft_fails_validation_until_a_person_verifies_something(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _ = make_draft(root)
            problems = validate(bundle, artifact_root=root)
        self.assertTrue(any("hypothesis" in item for item in problems))

    def test_marking_one_function_pass_makes_fixture_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _ = make_draft(root)
            test_bytes = b"synthetic graphics test output\\n"
            test_path = root / "artifacts" / "graphics-test.log"
            test_path.write_bytes(test_bytes)
            bundle["artifacts"].append({
                "kind": "functional-test-log",
                "path": "artifacts/graphics-test.log",
                "sha256": hashlib.sha256(test_bytes).hexdigest(),
            })
            bundle["verified_functions"][0]["status"] = "pass"
            bundle["verified_functions"][0]["evidence"] = ["artifacts/graphics-test.log"]
            problems = validate(bundle, artifact_root=root)
        self.assertEqual(problems, [])

    def test_known_problems_become_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = make_draft(Path(temporary))
        joined = " ".join(bundle["known_limitations"])
        self.assertIn("net-0", joined)
        self.assertIn("missing", joined)
        self.assertIn("network-link", joined)

    def test_pci_signature_is_lowercased_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = make_draft(Path(temporary))
        self.assertEqual(bundle["hardware_signature"]["pci_ids"], ["10de:1c82"])

    def test_no_signature_means_no_signature_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = make_draft(Path(temporary), report(devices=[]))
        self.assertNotIn("hardware_signature", bundle)

    def test_not_assessed_is_never_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, _ = make_draft(Path(temporary))
        self.assertTrue(bundle["not_assessed"])

    def test_source_report_is_a_hashed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle, raw = make_draft(Path(temporary))
        artifact = bundle["artifacts"][0]
        self.assertEqual(artifact["path"], REPORT_ARTIFACT)
        self.assertEqual(artifact["kind"], "wsm-hwcheck-report")
        self.assertEqual(artifact["sha256"], hashlib.sha256(raw).hexdigest())

    def test_profile_source_digest_is_bound_to_exact_profile_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _ = make_draft(root)
            original = bundle["profile_source"]["sha256"]
            (root / "profile.scm").write_bytes(b";; changed after test\n")
            problems = validate(bundle, artifact_root=root)
        self.assertTrue(any("profile_source/sha256 does not match" in item for item in problems))
        self.assertEqual(len(original), 64)

    def test_report_without_id_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            draft({"devices": [], "schema_version": "1.0.0", "collected_at": "2026-11-26"}, "ASUS", "H170-PRO", "asus/h170-pro", b"{}", b";; profile\n")

    def test_report_without_schema_version_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            draft({"devices": [], "report_id": "report-123", "collected_at": "2026-11-26"}, "ASUS", "H170-PRO", "asus/h170-pro", b"{}", b";; profile\n")


class CliTests(unittest.TestCase):
    def test_cli_writes_v2_bundle_and_exact_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            raw = json.dumps(report(), ensure_ascii=False).encode("utf-8")
            report_path.write_bytes(raw)
            profile_dir = directory / "profiles" / "asus" / "h170-pro"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.scm").write_bytes(PROFILE_SOURCE_BYTES)
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
            artifact_path = profile_dir / REPORT_ARTIFACT
            self.assertEqual(written["schema"], "wsm-profile-evidence/2")
            self.assertEqual(artifact_path.read_bytes(), raw)
            self.assertEqual(
                written["artifacts"][0]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(
                written["profile_source"]["sha256"],
                hashlib.sha256((profile_dir / "profile.scm").read_bytes()).hexdigest(),
            )

    def test_cli_refuses_to_overwrite_existing_evidence_or_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            report_path.write_text(json.dumps(report()), encoding="utf-8")
            profile_dir = directory / "profiles" / "asus" / "h170-pro"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.scm").write_bytes(PROFILE_SOURCE_BYTES)
            out = profile_dir / "evidence.json"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "draft_profile_evidence.py"),
                "--report", str(report_path),
                "--vendor", "ASUS",
                "--model", "H170-PRO",
                "--slug", "asus/h170-pro",
                "--out", str(out),
            ]
            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = out.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(out.read_bytes(), original)

    def test_cli_refuses_to_draft_without_profile_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "hw.json"
            report_path.write_text(json.dumps(report()), encoding="utf-8")
            profile_dir = directory / "profiles" / "asus" / "h170-pro"
            profile_dir.mkdir(parents=True)
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
            self.assertFalse(out.exists())
            self.assertFalse((profile_dir / REPORT_ARTIFACT).exists())

    def test_cli_rejects_invalid_utf8_source_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report_path = directory / "bad.json"
            report_path.write_bytes(b"\xff\xfe")
            profile_dir = directory / "profile"
            profile_dir.mkdir()
            (profile_dir / "profile.scm").write_bytes(PROFILE_SOURCE_BYTES)
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
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
