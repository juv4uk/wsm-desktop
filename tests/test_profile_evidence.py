# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules for hardware profile evidence bundles and referenced artifact bytes."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_profile_evidence import (  # noqa: E402
    discover_profiles,
    main,
    validate,
    validate_directory,
    read_document,
)

BASE = {
    "schema": "wsm-profile-evidence/1",
    "profile": {"vendor": "ASUS", "model": "H170-PRO", "slug": "asus/h170-pro"},
    "report_id": "0f3c9a1e-2b44-4c8d-9f10-77a1b2c3d4e5",
    "report_schema_version": "1.0.0",
    "isa_level": "x86-64-v2",
    "verified_on": "2026-11-26",
    "verified_by": "автори проєкту",
    "verified_functions": [
        {"name": "graphics", "status": "pass", "note": "synthetic fixture only"},
        {"name": "storage", "status": "pass"},
    ],
    "known_limitations": ["NVK reclocking unavailable on Pascal"],
    "not_assessed": ["suspend/resume", "audio over HDMI"],
    "artifacts": [
        {
            "kind": "dmesg",
            "path": "artifacts/dmesg.txt",
            "sha256": "a" * 64,
            "note": "synthetic fixture only",
        }
    ],
}


def bundle(**overrides) -> dict:
    document = copy.deepcopy(BASE)
    document.update(overrides)
    return document


def write_profile(root: Path, artifact_bytes: bytes = b"synthetic dmesg\n") -> Path:
    profile_dir = root / "asus" / "h170-pro"
    artifact_dir = profile_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (profile_dir / "profile.scm").write_text(";; synthetic test fixture\n", encoding="utf-8")
    artifact = artifact_dir / "dmesg.txt"
    artifact.write_bytes(artifact_bytes)

    document = bundle()
    document["artifacts"][0]["sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
    evidence = profile_dir / "evidence.json"
    evidence.write_text(json.dumps(document), encoding="utf-8")
    return evidence


class ShapeTests(unittest.TestCase):
    def test_minimal_bundle_is_accepted_by_schema(self) -> None:
        self.assertEqual(validate(bundle()), [])

    def test_missing_isa_level_is_refused(self) -> None:
        document = bundle()
        del document["isa_level"]
        self.assertTrue(validate(document))

    def test_missing_artifacts_is_refused(self) -> None:
        document = bundle()
        del document["artifacts"]
        self.assertTrue(validate(document))

    def test_invalid_calendar_date_is_refused(self) -> None:
        problems = validate(bundle(verified_on="2026-99-99"))
        self.assertTrue(any("date" in problem.lower() for problem in problems))

    def test_empty_artifacts_is_refused(self) -> None:
        self.assertTrue(validate(bundle(artifacts=[])))

    def test_missing_artifact_path_is_refused(self) -> None:
        self.assertTrue(validate(bundle(artifacts=[{"kind": "dmesg", "sha256": "a" * 64}])))

    def test_artifact_needs_a_hash(self) -> None:
        self.assertTrue(validate(bundle(artifacts=[{"kind": "dmesg", "path": "artifacts/dmesg.txt"}])))

    def test_artifact_with_hash_and_path_is_accepted_by_schema(self) -> None:
        self.assertEqual(validate(bundle()), [])

    def test_missing_not_assessed_is_refused(self) -> None:
        document = bundle()
        del document["not_assessed"]
        self.assertTrue(validate(document))

    def test_empty_not_assessed_is_refused(self) -> None:
        self.assertTrue(validate(bundle(not_assessed=[])))

    def test_unknown_status_is_refused(self) -> None:
        document = bundle(verified_functions=[{"name": "graphics", "status": "probably"}])
        self.assertTrue(validate(document))


class ArtifactTests(unittest.TestCase):
    def test_artifact_hash_is_verified_against_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(validate(document, artifact_root=evidence.parent), [])

    def test_artifact_hash_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            document["artifacts"][0]["sha256"] = "0" * 64
            problems = validate(document, artifact_root=evidence.parent)
            self.assertTrue(any("sha256 mismatch" in problem for problem in problems))

    def test_artifact_path_traversal_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            document["artifacts"][0]["path"] = "../outside.txt"
            problems = validate(document, artifact_root=evidence.parent)
            self.assertTrue(any("safe relative path" in problem for problem in problems))

    def test_windows_drive_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            document["artifacts"][0]["path"] = "C:/outside.txt"
            problems = validate(document, artifact_root=evidence.parent)
            self.assertTrue(any("safe relative path" in problem for problem in problems))

    def test_artifact_path_with_dot_segment_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            document["artifacts"][0]["path"] = "./artifacts/dmesg.txt"
            problems = validate(document, artifact_root=evidence.parent)
            self.assertTrue(any("safe relative path" in problem for problem in problems))

    def test_missing_artifact_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = write_profile(root)
            document = json.loads(evidence.read_text(encoding="utf-8"))
            (evidence.parent / "artifacts" / "dmesg.txt").unlink()
            problems = validate(document, artifact_root=evidence.parent)
            self.assertTrue(any("missing" in problem for problem in problems))


class RuleTests(unittest.TestCase):
    def test_bundle_without_a_pass_is_refused(self) -> None:
        document = bundle(
            verified_functions=[{"name": "graphics", "status": "not-assessed"}]
        )
        problems = validate(document)
        self.assertTrue(any("hypothesis" in problem for problem in problems))

    def test_failure_must_appear_in_known_limitations(self) -> None:
        document = bundle(
            verified_functions=[
                {"name": "graphics", "status": "pass"},
                {"name": "wifi", "status": "fail"},
            ]
        )
        problems = validate(document)
        self.assertTrue(any("wifi" in problem for problem in problems))

    def test_failure_listed_in_limitations_is_accepted(self) -> None:
        document = bundle(
            verified_functions=[
                {"name": "graphics", "status": "pass"},
                {"name": "wifi", "status": "fail"},
            ],
            known_limitations=["wifi does not associate on 5 GHz"],
        )
        self.assertEqual(validate(document), [])

    def test_verified_by_only_accepts_nonpersonal_roles(self) -> None:
        self.assertEqual(validate(bundle(verified_by="local agent")), [])
        self.assertEqual(validate(bundle(verified_by="web agent")), [])
        self.assertTrue(validate(bundle(verified_by="John Smith")))
        self.assertTrue(validate(bundle(verified_by="someone@example.com")))


class DirectoryTests(unittest.TestCase):
    def test_profile_without_evidence_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "vendor" / "model"
            profile_dir.mkdir(parents=True)
            (profile_dir / "profile.scm").write_text(";; fixture\n", encoding="utf-8")
            profiles, evidence, problems = discover_profiles(root)
            self.assertEqual(len(profiles), 1)
            self.assertEqual(evidence, [])
            self.assertTrue(any("has no evidence.json" in problem for problem in problems))

    def test_evidence_without_profile_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "asus" / "h170-pro"
            profile_dir.mkdir(parents=True)
            (profile_dir / "evidence.json").write_text("{}", encoding="utf-8")
            _, _, problems = discover_profiles(root)
            self.assertTrue(any("no matching profile.scm" in problem for problem in problems))

    def test_custom_directory_root_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "nonstandard-root"
            evidence = write_profile(root)
            self.assertEqual(validate_directory(evidence, root), [])

    def test_invalid_utf8_evidence_is_a_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_bytes(bytes([0xFF, 0xFE]))
            document, problems = read_document(evidence)
        self.assertIsNone(document)
        self.assertTrue(any("cannot read evidence JSON" in problem for problem in problems))

    def test_main_accepts_a_valid_custom_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "nonstandard-root"
            evidence = write_profile(root)
            self.assertEqual(main(["--dir", str(root)]), 0)
            self.assertTrue(evidence.is_file())


class RepositoryTests(unittest.TestCase):
    def test_schema_file_is_valid_json(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "profile-evidence.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["title"], "WSM hardware profile evidence")
        self.assertIn("isa_level", schema["required"])
        self.assertIn("artifacts", schema["required"])

    def test_no_bundle_lives_outside_the_profiles_tree(self) -> None:
        strays = [
            path for path in ROOT.rglob("evidence.json")
            if "profiles/hardware" not in path.as_posix()
        ]
        self.assertEqual(strays, [])


if __name__ == "__main__":
    unittest.main()
