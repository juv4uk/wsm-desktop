# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules for hardware profile evidence bundles."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from check_profile_evidence import validate  # noqa: E402

BASE = {
    "schema": "wsm-profile-evidence/1",
    "profile": {"vendor": "Gigabyte", "model": "GA-H170-Gaming3", "slug": "gigabyte/ga-h170-gaming3"},
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
}


def bundle(**overrides) -> dict:
    document = copy.deepcopy(BASE)
    document.update(overrides)
    return document


class ShapeTests(unittest.TestCase):
    def test_minimal_bundle_is_accepted(self) -> None:
        self.assertEqual(validate(bundle()), [])

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
        document = bundle(artifacts=[{"kind": "dmesg"}])
        self.assertTrue(validate(document))

    def test_artifact_with_hash_is_accepted(self) -> None:
        document = bundle(artifacts=[{"kind": "dmesg", "sha256": "a" * 64}])
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


class InstallerGateTests(unittest.TestCase):
    """The documented rule must hold in code, not only in prose."""

    def plan(self, evidence=None):
        sys.path.insert(0, str(ROOT))
        from wsm_install.plan import build_plan

        report = {
            "schema_version": "1.0.0",
            "report_id": "0f3c9a1e-2b44-4c8d-9f10-77a1b2c3d4e5",
            "collected_at": "2026-11-26T00:00:00Z",
            "collectors": [],
            "environment": {
                "architecture": "x86_64",
                "kernel_release": "6.17.0",
                "boot_mode": "uefi",
                "virtualization": "none",
            },
            "limitations": [],
            "privacy": {"personal_data_collected": False},
            "devices": [],
            "warnings": [],
        }
        import json as _json
        payload = _json.dumps(report).encode("utf-8")
        return build_plan(report, payload, "guix", profile_evidence=evidence)

    def test_absent_evidence_is_a_warning_not_a_blocker(self) -> None:
        """Most machines are untested; that must not look like a broken profile."""
        _, blockers, warnings = self.plan(None)
        self.assertEqual(blockers, [])
        self.assertTrue(any("no verified hardware profile" in w for w in warnings))

    def test_broken_evidence_blocks_the_plan(self) -> None:
        broken = bundle(verified_functions=[{"name": "graphics", "status": "not-assessed"}])
        _, blockers, _ = self.plan(broken)
        self.assertTrue(any("hardware profile evidence is not valid" in b for b in blockers))

    def test_valid_evidence_produces_no_evidence_blocker(self) -> None:
        _, blockers, warnings = self.plan(bundle())
        self.assertFalse(any("hardware profile evidence" in b for b in blockers))
        self.assertFalse(any("no verified hardware profile" in w for w in warnings))


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


class OwnerReferenceSeparationTests(unittest.TestCase):
    def test_owner_hardware_reference_is_outside_profile_discovery(self) -> None:
        owner_reference = ROOT / "docs" / "hardware" / "OWNER-HARDWARE-REFERENCE.md"
        self.assertTrue(owner_reference.is_file())
        self.assertFalse((ROOT / "profiles" / "hardware" / "gigabyte" / "ga-h170-gaming3" / "README.md").exists())
        content = owner_reference.read_text(encoding="utf-8")
        self.assertIn("не hardware evidence bundle", content)
        self.assertIn("native Linux", content)
        self.assertIn("not-assessed", content)

    def test_profile_catalog_points_to_separate_owner_reference(self) -> None:
        catalog = (ROOT / "profiles" / "hardware" / "README.md").read_text(encoding="utf-8")
        self.assertIn("OWNER-HARDWARE-REFERENCE.md", catalog)
        self.assertIn("оголошених апаратних профілів", catalog)

if __name__ == "__main__":
    unittest.main()
