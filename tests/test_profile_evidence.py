# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules for hardware profile evidence bundles."""

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

from check_profile_evidence import validate, validate_directory  # noqa: E402

ARTIFACT_BYTES = b"kernel log\\n"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT_BYTES).hexdigest()

BASE = {
    "schema": "wsm-profile-evidence/1",
    "profile": {"vendor": "ASUS", "model": "H170-PRO", "slug": "asus/h170-pro"},
    "report_id": "0f3c9a1e-2b44-4c8d-9f10-77a1b2c3d4e5",
    "report_schema_version": "1.0.0",
    "isa_level": "x86-64-v2",
    "verified_on": "2026-11-26",
    "verified_by": "автори проєкту",
    "verified_functions": [
        {"name": "graphics", "status": "pass", "note": "i915, 1080p"},
        {"name": "storage", "status": "pass"},
    ],
    "known_limitations": ["NVK reclocking unavailable on Pascal"],
    "not_assessed": ["suspend/resume", "audio over HDMI"],
    "artifacts": [
        {"kind": "dmesg", "path": "artifacts/dmesg.txt", "sha256": ARTIFACT_HASH}
    ],
}


def bundle(**overrides) -> dict:
    document = copy.deepcopy(BASE)
    document.update(overrides)
    return document


class ShapeTests(unittest.TestCase):
    def test_minimal_bundle_is_accepted(self) -> None:
        self.assertEqual(validate(bundle()), [])

    def test_missing_isa_level_is_refused(self) -> None:
        document = bundle()
        del document["isa_level"]
        self.assertTrue(validate(document))

    def test_missing_artifacts_is_refused(self) -> None:
        document = bundle()
        del document["artifacts"]
        self.assertTrue(validate(document))

    def test_empty_artifacts_is_refused(self) -> None:
        self.assertTrue(validate(bundle(artifacts=[])))

    def test_artifact_path_must_be_bundle_relative(self) -> None:
        document = bundle(
            artifacts=[{"kind": "dmesg", "path": "../dmesg.txt", "sha256": ARTIFACT_HASH}]
        )
        self.assertTrue(validate(document))

    def test_missing_not_assessed_is_refused(self) -> None:
        document = bundle()
        del document["not_assessed"]
        self.assertTrue(validate(document))

    def test_empty_not_assessed_is_refused(self) -> None:
        """No profile is fully verified; an empty list claims otherwise."""
        self.assertTrue(validate(bundle(not_assessed=[])))

    def test_unknown_status_is_refused(self) -> None:
        document = bundle(
            verified_functions=[{"name": "graphics", "status": "probably"}]
        )
        self.assertTrue(validate(document))

    def test_artifact_needs_a_hash(self) -> None:
        document = bundle(artifacts=[{"kind": "dmesg", "path": "artifacts/dmesg.txt"}])
        self.assertTrue(validate(document))

    def test_artifact_with_hash_is_accepted(self) -> None:
        document = bundle(artifacts=[{"kind": "dmesg", "path": "artifacts/dmesg.txt", "sha256": "a" * 64}])
        self.assertEqual(validate(document), [])


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

    def test_email_in_verified_by_is_refused(self) -> None:
        problems = validate(bundle(verified_by="someone@example.com"))
        self.assertTrue(any("e-mail" in problem for problem in problems))

    def test_personal_name_is_allowed_but_discouraged(self) -> None:
        """The rule bans e-mail, not names; docs tell contributors what to use."""
        self.assertEqual(validate(bundle(verified_by="local agent")), [])


class DirectoryTests(unittest.TestCase):
    def test_custom_profile_root_checks_artifact_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_dir = root / "acme" / "test-board"
            artifacts_dir = profile_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            (artifacts_dir / "dmesg.txt").write_bytes(ARTIFACT_BYTES)
            document = bundle(
                profile={"vendor": "ACME", "model": "Test Board", "slug": "acme/test-board"}
            )
            evidence = profile_dir / "evidence.json"
            evidence.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(validate_directory(evidence, root), [])

    def test_artifact_digest_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_dir = root / "acme" / "test-board"
            artifacts_dir = profile_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            (artifacts_dir / "dmesg.txt").write_bytes(ARTIFACT_BYTES)
            document = bundle(
                profile={"vendor": "ACME", "model": "Test Board", "slug": "acme/test-board"},
                artifacts=[
                    {"kind": "dmesg", "path": "artifacts/dmesg.txt", "sha256": "0" * 64}
                ],
            )
            evidence = profile_dir / "evidence.json"
            evidence.write_text(json.dumps(document), encoding="utf-8")
            problems = validate_directory(evidence, root)
            self.assertTrue(any("SHA-256 mismatch" in problem for problem in problems))


class RepositoryTests(unittest.TestCase):
    def test_schema_file_is_valid_json(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "profile-evidence.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["title"], "WSM hardware profile evidence")

    def test_no_bundle_lives_outside_the_profiles_tree(self) -> None:
        """A bundle next to the code would be a claim nobody can find."""
        strays = [
            path for path in ROOT.rglob("evidence.json")
            if "profiles/hardware" not in path.as_posix()
        ]
        self.assertEqual(strays, [])


if __name__ == "__main__":
    unittest.main()
