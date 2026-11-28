# SPDX-License-Identifier: LicenseRef-Volnist
"""Rules for hardware profile evidence and the files it references."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_profile_evidence import main, validate, validate_directory  # noqa: E402
from wsm_install.plan import build_plan  # noqa: E402

ARTIFACT_BYTES = b"synthetic functional test output\n"
ARTIFACT_SHA256 = hashlib.sha256(ARTIFACT_BYTES).hexdigest()
PROFILE_SOURCE_BYTES = b";; synthetic profile source\n"
PROFILE_SOURCE_SHA256 = hashlib.sha256(PROFILE_SOURCE_BYTES).hexdigest()
SOURCE_REPORT_BYTES = (ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json").read_bytes()
SOURCE_REPORT = json.loads(SOURCE_REPORT_BYTES)
SOURCE_REPORT_SHA256 = hashlib.sha256(SOURCE_REPORT_BYTES).hexdigest()

BASE = {
    "schema": "wsm-profile-evidence/2",
    "profile": {"vendor": "Gigabyte", "model": "GA-H170-Gaming 3", "slug": "gigabyte/ga-h170-gaming3"},
    "report_id": SOURCE_REPORT["report_id"],
    "report_schema_version": SOURCE_REPORT["schema_version"],
    "profile_source": {"path": "profile.scm", "sha256": PROFILE_SOURCE_SHA256},
    "isa_level": "x86-64-v3",
    "verified_on": "2026-11-26",
    "verified_by": "автори проєкту",
    "verified_functions": [
        {"name": "graphics", "status": "pass", "note": "synthetic fixture only", "evidence": ["artifacts/functional-test.log"]},
        {"name": "storage", "status": "pass", "evidence": ["artifacts/functional-test.log"]},
    ],
    "known_limitations": ["NVK reclocking unavailable on Pascal"],
    "not_assessed": ["suspend/resume", "audio over HDMI"],
    "artifacts": [
        {"kind": "functional-test-log", "path": "artifacts/functional-test.log", "sha256": ARTIFACT_SHA256},
        {"kind": "wsm-hwcheck-report", "path": "artifacts/wsm-hwcheck-report.json", "sha256": SOURCE_REPORT_SHA256},
    ],
}


def bundle(**overrides) -> dict:
    document = copy.deepcopy(BASE)
    document.update(overrides)
    return document


def prepare_artifact_root(root: Path, source_report_bytes: bytes = SOURCE_REPORT_BYTES) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "profile.scm").write_bytes(PROFILE_SOURCE_BYTES)
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "functional-test.log").write_bytes(ARTIFACT_BYTES)
    (artifact_dir / "wsm-hwcheck-report.json").write_bytes(source_report_bytes)


def validate_fixture(document: dict | None = None) -> list[str]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        prepare_artifact_root(root)
        return validate(bundle() if document is None else document, artifact_root=root)



class ArtifactIdentityTests(unittest.TestCase):
    def test_duplicate_artifact_paths_are_rejected_even_with_different_kinds(self) -> None:
        document = bundle()
        duplicate = copy.deepcopy(document["artifacts"][0])
        duplicate["kind"] = "wsm-hwcheck-report"
        document["artifacts"].append(duplicate)
        problems = validate_fixture(document)
        self.assertTrue(any("duplicate artifact path" in item for item in problems))

    def test_copy_of_source_report_bytes_cannot_be_relabelled_as_functional(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_artifact_root(root)
            copied = root / "artifacts" / "copied-report.log"
            copied.write_bytes(SOURCE_REPORT_BYTES)
            document = bundle()
            document["artifacts"].append({
                "kind": "functional-test-log",
                "path": "artifacts/copied-report.log",
                "sha256": SOURCE_REPORT_SHA256,
            })
            document["verified_functions"][0]["evidence"] = ["artifacts/copied-report.log"]
            problems = validate(document, artifact_root=root)
        self.assertTrue(any("bytes identical to the source hardware report" in item for item in problems))

    def test_shared_validator_requires_exactly_one_source_report_artifact(self) -> None:
        document = bundle()
        document["artifacts"] = [
            item for item in document["artifacts"]
            if item["kind"] != "wsm-hwcheck-report"
        ]
        problems = validate_fixture(document)
        self.assertTrue(any("exactly one wsm-hwcheck-report" in item for item in problems))

    def test_shared_validator_rejects_multiple_source_report_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_artifact_root(root)
            duplicate_path = root / "artifacts" / "second-report.json"
            duplicate_path.write_bytes(SOURCE_REPORT_BYTES)
            document = bundle()
            document["artifacts"].append({
                "kind": "wsm-hwcheck-report",
                "path": "artifacts/second-report.json",
                "sha256": SOURCE_REPORT_SHA256,
            })
            problems = validate(document, artifact_root=root)
        self.assertTrue(any("exactly one wsm-hwcheck-report" in item for item in problems))

    def test_artifact_path_must_be_under_artifacts_directory(self) -> None:
        document = bundle()
        document["artifacts"][0]["path"] = "README.md"
        problems = validate_fixture(document)
        self.assertTrue(any("artifacts/" in item for item in problems))

    def test_zero_byte_functional_log_is_rejected_even_with_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_artifact_root(root)
            (root / "artifacts" / "functional-test.log").write_bytes(b"")
            document = bundle()
            document["artifacts"][0]["sha256"] = hashlib.sha256(b"").hexdigest()
            problems = validate(document, artifact_root=root)
        self.assertTrue(any("empty file" in item for item in problems))
    def test_unknown_artifact_kind_is_rejected(self) -> None:
        document = bundle()
        document["artifacts"][0]["kind"] = "mystery-proof"
        problems = validate_fixture(document)
        self.assertTrue(any("kind" in item for item in problems))


class ShapeTests(unittest.TestCase):
    def test_minimal_bundle_with_verified_artifact_is_accepted(self) -> None:
        self.assertEqual(validate_fixture(), [])

    def test_invalid_calendar_date_is_refused(self) -> None:
        problems = validate_fixture(bundle(verified_on="2026-99-99"))
        self.assertTrue(any("format" in item.lower() or "date" in item.lower() for item in problems))

    def test_missing_isa_level_is_refused(self) -> None:
        document = bundle()
        del document["isa_level"]
        self.assertTrue(validate_fixture(document))

    def test_missing_artifacts_is_refused(self) -> None:
        document = bundle()
        del document["artifacts"]
        self.assertTrue(validate_fixture(document))

    def test_empty_artifacts_is_refused(self) -> None:
        self.assertTrue(validate_fixture(bundle(artifacts=[])))

    def test_missing_not_assessed_is_refused(self) -> None:
        document = bundle()
        del document["not_assessed"]
        self.assertTrue(validate_fixture(document))

    def test_empty_not_assessed_is_refused(self) -> None:
        self.assertTrue(validate_fixture(bundle(not_assessed=[])))

    def test_unknown_status_is_refused(self) -> None:
        document = bundle(
            verified_functions=[{"name": "graphics", "status": "probably"}]
        )
        self.assertTrue(validate_fixture(document))


class ArtifactTests(unittest.TestCase):
    def test_artifact_sha256_is_checked_against_real_bytes(self) -> None:
        self.assertEqual(validate_fixture(), [])
        document = bundle(
            artifacts=[
                {"kind": "functional-test-log", "path": "artifacts/functional-test.log", "sha256": "0" * 64}
            ]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("does not match the bytes" in item for item in problems))

    def test_missing_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problems = validate(bundle(), artifact_root=root)
        self.assertTrue(any("is missing or escapes the evidence directory" in item for item in problems))

    def test_artifact_path_cannot_escape_bundle_directory(self) -> None:
        document = bundle(
            artifacts=[
                {"kind": "functional-test-log", "path": "../outside.txt", "sha256": ARTIFACT_SHA256}
            ]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("safe relative path" in item for item in problems))

    def test_absolute_artifact_path_is_rejected(self) -> None:
        document = bundle(
            artifacts=[
                {"kind": "functional-test-log", "path": "/etc/passwd", "sha256": ARTIFACT_SHA256}
            ]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("safe relative path" in item for item in problems))

    def test_artifact_requires_an_evidence_root(self) -> None:
        problems = validate(bundle())
        self.assertTrue(any("without an evidence directory" in item for item in problems))

    def test_artifact_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_artifact_root(root)
            target = root / "artifacts" / "functional-test.log"
            real_file = root / "artifacts" / "real-functional-test.log"
            target.rename(real_file)
            target.symlink_to(real_file)
            problems = validate(bundle(), artifact_root=root)
        self.assertTrue(any("symbolic link" in item for item in problems))


class RuleTests(unittest.TestCase):
    def test_bundle_without_a_pass_is_refused(self) -> None:
        document = bundle(
            verified_functions=[{"name": "graphics", "status": "not-assessed"}]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("hypothesis" in problem for problem in problems))

    def test_failure_must_appear_in_known_limitations(self) -> None:
        document = bundle(
            verified_functions=[
                {"name": "graphics", "status": "pass", "evidence": ["artifacts/functional-test.log"]},
                {"name": "wifi", "status": "fail", "evidence": ["artifacts/functional-test.log"]},
            ]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("wifi" in problem for problem in problems))

    def test_pass_requires_a_functional_evidence_reference(self) -> None:
        document = bundle()
        document["verified_functions"][0].pop("evidence")
        problems = validate_fixture(document)
        self.assertTrue(any("cites no functional evidence artifact" in item for item in problems))

    def test_function_evidence_reference_must_exist(self) -> None:
        document = bundle()
        document["verified_functions"][0]["evidence"] = ["artifacts/missing.log"]
        problems = validate_fixture(document)
        self.assertTrue(any("references missing artifact" in item for item in problems))

    def test_source_report_is_not_functional_test_evidence(self) -> None:
        document = bundle(
            artifacts=[{
                "kind": "wsm-hwcheck-report",
                "path": "artifacts/functional-test.log",
                "sha256": ARTIFACT_SHA256,
            }]
        )
        problems = validate_fixture(document)
        self.assertTrue(any("non-functional artifact kind" in item for item in problems))

    def test_failure_listed_in_limitations_is_accepted(self) -> None:
        document = bundle(
            verified_functions=[
                {"name": "graphics", "status": "pass", "evidence": ["artifacts/functional-test.log"]},
                {"name": "wifi", "status": "fail", "evidence": ["artifacts/functional-test.log"]},
            ],
            known_limitations=["wifi does not associate on 5 GHz"],
        )
        self.assertEqual(validate_fixture(document), [])

    def test_only_repository_verifier_roles_are_allowed(self) -> None:
        for verifier in ("автори проєкту", "local agent", "web agent"):
            with self.subTest(verifier=verifier):
                self.assertEqual(validate_fixture(bundle(verified_by=verifier)), [])

    def test_personal_name_is_rejected(self) -> None:
        problems = validate_fixture(bundle(verified_by="Example Person"))
        self.assertTrue(any("verified_by" in problem for problem in problems))

    def test_email_is_rejected(self) -> None:
        problems = validate_fixture(bundle(verified_by="someone@example.com"))
        self.assertTrue(any("verified_by" in problem for problem in problems))


class InstallerPlanGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        report_path = ROOT / "tests" / "fixtures" / "hardware" / "desktop-observed.json"
        cls.report_bytes = report_path.read_bytes()
        cls.report = json.loads(cls.report_bytes)

    def matching_bundle(self) -> dict:
        document = bundle(
            report_id=self.report["report_id"],
            report_schema_version=self.report["schema_version"],
        )
        source = next(item for item in document["artifacts"] if item["kind"] == "wsm-hwcheck-report")
        source["sha256"] = hashlib.sha256(self.report_bytes).hexdigest()
        return document

    def build(self, evidence: dict, root: Path | None):
        return build_plan(
            self.report,
            self.report_bytes,
            "guix",
            profile_evidence=evidence,
            profile_evidence_root=root,
        )

    def test_build_plan_accepts_only_matching_report_and_verified_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            plan, blockers, _warnings = self.build(self.matching_bundle(), root)
        self.assertFalse(any("hardware profile evidence is not valid" in item for item in blockers))
        self.assertIsNotNone(plan["profile_evidence"])
        self.assertEqual(plan["profile_evidence"]["report_id"], self.report["report_id"])

    def test_build_plan_rejects_artifact_bytes_changed_after_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            (root / "artifacts" / "functional-test.log").write_bytes(b"tampered after manifest creation")
            _plan, blockers, _warnings = self.build(self.matching_bundle(), root)
        self.assertTrue(any("does not match the bytes" in item for item in blockers))

    def test_build_plan_rejects_profile_evidence_from_another_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            evidence = self.matching_bundle()
            evidence["report_id"] = "another-report-id"
            _plan, blockers, _warnings = self.build(evidence, root)
        self.assertTrue(any("report_id does not match" in item for item in blockers))

    def test_build_plan_rejects_profile_evidence_from_another_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            evidence = self.matching_bundle()
            evidence["report_schema_version"] = "9.9.9"
            _plan, blockers, _warnings = self.build(evidence, root)
        self.assertTrue(any("report_schema_version does not match" in item for item in blockers))

    def test_build_plan_rejects_missing_profile_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            (root / "profile.scm").unlink()
            _plan, blockers, _warnings = self.build(self.matching_bundle(), root)
        self.assertTrue(any("no regular profile.scm" in item for item in blockers))

    def test_build_plan_rejects_profile_slug_for_another_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            evidence = self.matching_bundle()
            evidence["profile"]["slug"] = "gigabyte/different-board"
            _plan, blockers, _warnings = self.build(evidence, root)
        self.assertTrue(any("does not match the directory" in item for item in blockers))

    def test_build_plan_rejects_profile_source_modified_after_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(root, self.report_bytes)
            (root / "profile.scm").write_bytes(b";; changed after verification\\n")
            _plan, blockers, _warnings = self.build(self.matching_bundle(), root)
        self.assertTrue(any("profile_source/sha256 does not match" in item for item in blockers))

    def test_build_plan_rejects_source_report_bytes_with_same_report_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
            changed_report = self.report_bytes + b"\\n"
            prepare_artifact_root(root, changed_report)
            evidence = self.matching_bundle()
            source = next(item for item in evidence["artifacts"] if item["kind"] == "wsm-hwcheck-report")
            source["sha256"] = hashlib.sha256(changed_report).hexdigest()
            _plan, blockers, _warnings = self.build(evidence, root)
        self.assertTrue(any("source-report SHA-256 does not match" in item for item in blockers))

    def test_build_plan_requires_exactly_one_source_report_artifact(self) -> None:
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "gigabyte" / "ga-h170-gaming3"
                prepare_artifact_root(root, self.report_bytes)
                evidence = self.matching_bundle()
                source = next(item for item in evidence["artifacts"] if item["kind"] == "wsm-hwcheck-report")
                if mode == "missing":
                    evidence["artifacts"].remove(source)
                else:
                    evidence["artifacts"].append(copy.deepcopy(source))
                _plan, blockers, _warnings = self.build(evidence, root)
            self.assertTrue(any("exactly one wsm-hwcheck-report" in item for item in blockers))

    def test_build_plan_fails_closed_when_artifact_root_is_missing(self) -> None:
        _plan, blockers, _warnings = self.build(self.matching_bundle(), None)
        self.assertTrue(any("without an evidence directory" in item for item in blockers))


class DirectoryTests(unittest.TestCase):
    def test_model_directory_without_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "gigabyte" / "ga-h170-gaming3"
            model.mkdir(parents=True)
            (model / "profile.scm").write_text(";; declared profile without evidence\\n", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["--dir", str(root)])
        self.assertEqual(result, 1)
        self.assertIn("missing mandatory evidence.json", stderr.getvalue())

    def test_readme_only_research_directory_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "gigabyte" / "ga-h170-gaming3"
            model.mkdir(parents=True)
            (model / "README.md").write_text("# Owner reference\\n", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["--dir", str(root)])
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertIn("no hardware profile directories yet", stdout.getvalue())

    def test_empty_profiles_root_is_not_a_fake_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--dir", temporary])
        self.assertEqual(result, 0)
        self.assertIn("no hardware profile directories yet", stdout.getvalue())

    def test_evidence_without_profile_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(model)
            (model / "profile.scm").unlink()
            evidence = bundle(profile={
                "vendor": "GIGABYTE",
                "model": "GA-H170-Gaming 3",
                "slug": "gigabyte/ga-h170-gaming3",
            })
            (model / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main(["--dir", str(root)])
        self.assertEqual(result, 1)
        self.assertIn("missing mandatory profile.scm", stderr.getvalue())


    def test_directory_slug_must_match_vendor_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(model)
            profile_bytes = b";; Synthetic test profile\n"
            (model / "profile.scm").write_bytes(profile_bytes)
            evidence = model / "evidence.json"
            document = bundle(
                profile={
                    "vendor": "GIGABYTE",
                    "model": "GA-H170-Gaming 3",
                    "slug": "gigabyte/different-board",
                }
            )
            document["profile_source"]["sha256"] = hashlib.sha256(profile_bytes).hexdigest()
            evidence.write_text(json.dumps(document), encoding="utf-8")
            problems = validate_directory(evidence, root)
        self.assertTrue(any("does not match the directory" in item for item in problems))

    def test_valid_directory_and_artifact_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "gigabyte" / "ga-h170-gaming3"
            prepare_artifact_root(model)
            profile_bytes = b";; synthetic fixture\n"
            (model / "profile.scm").write_bytes(profile_bytes)
            evidence = model / "evidence.json"
            document = bundle(
                profile={
                    "vendor": "GIGABYTE",
                    "model": "GA-H170-Gaming 3",
                    "slug": "gigabyte/ga-h170-gaming3",
                }
            )
            document["profile_source"]["sha256"] = hashlib.sha256(profile_bytes).hexdigest()
            evidence.write_text(json.dumps(document), encoding="utf-8")
            problems = validate_directory(evidence, root)
        self.assertEqual(problems, [])


class RepositoryTests(unittest.TestCase):
    def test_schema_file_is_valid_json(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "profile-evidence.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["title"], "WSM hardware profile evidence")
        self.assertEqual(schema["properties"]["schema"]["const"], "wsm-profile-evidence/2")
        self.assertEqual(
            schema["properties"]["artifacts"]["items"]["properties"]["kind"]["enum"],
            ["wsm-hwcheck-report", "functional-test-log"],
        )
        self.assertIn("isa_level", schema["required"])
        self.assertIn("artifacts", schema["required"])
        self.assertIn("profile_source", schema["required"])
        self.assertEqual(schema["properties"]["profile_source"]["properties"]["path"]["const"], "profile.scm")

    def test_no_bundle_lives_outside_the_profiles_tree(self) -> None:
        strays = [
            path for path in ROOT.rglob("evidence.json")
            if "profiles/hardware" not in path.as_posix()
        ]
        self.assertEqual(strays, [])

class ProfileTemplateTests(unittest.TestCase):
    """A template is not a profile, but it must still be honest about gaps."""

    def setUp(self) -> None:
        self.text = (ROOT / "profiles" / "hardware" / "template.scm").read_text(encoding="utf-8")

    def test_template_marks_every_value_that_needs_the_real_machine(self) -> None:
        self.assertGreaterEqual(self.text.count("ЗАМІНИТИ"), 5)

    def test_template_says_it_is_not_a_profile(self) -> None:
        self.assertIn("Не є профілем", self.text)

    def test_template_forbids_mixing_gpu_drivers(self) -> None:
        """Nouveau and the proprietary module in one boot profile is a known trap."""
        self.assertIn("Не змішуйте nouveau", self.text)

    def test_template_is_free_only_and_not_a_compatibility_toggle(self) -> None:
        self.assertIn("лише H170 Free candidate", self.text)
        self.assertIn("(kernel linux-libre)", self.text)
        self.assertIn("Compatibility — окрема конфігурація", self.text)
        self.assertNotIn("profile-variant", self.text)
        self.assertNotIn("nonguix linux", self.text)

    def test_template_points_at_the_evidence_rule(self) -> None:
        self.assertIn("profiles/hardware/README.md", self.text)

    def test_the_readme_links_the_template(self) -> None:
        readme = (ROOT / "profiles" / "hardware" / "README.md").read_text(encoding="utf-8")
        self.assertIn("template.scm", readme)



if __name__ == "__main__":
    unittest.main()
