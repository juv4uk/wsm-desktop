# SPDX-License-Identifier: LicenseRef-Volnist
"""Every artifact reader must accept its current version and refuse the next one.

The positive cases matter: a reader that refuses everything also satisfies a
negative-only test. These fixtures exercise the current profile-evidence v2,
hardware-report v1.0.0 and release-info v1 contracts.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install import preflight_env, profile  # noqa: E402


def profile_bundle(root: Path) -> dict:
    """Create a complete v2 bundle whose hashes point at real temporary files."""
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    profile_bytes = b";; test-only profile source\\n"
    report_bytes = json.dumps(
        {"report_id": "fixture-report-20261126", "schema_version": "1.0.0"}
    ).encode("utf-8")
    log_bytes = b"functional test: fixture graphics smoke passed\\n"
    (root / "profile.scm").write_bytes(profile_bytes)
    (artifacts / "wsm-hwcheck-report.json").write_bytes(report_bytes)
    (artifacts / "functional-test.log").write_bytes(log_bytes)

    digest = lambda value: hashlib.sha256(value).hexdigest()
    return {
        "schema": "wsm-profile-evidence/2",
        "profile": {
            "vendor": "Gigabyte",
            "model": "GA-H170-Gaming 3",
            "slug": "gigabyte/ga-h170-gaming3",
        },
        "report_id": "fixture-report-20261126",
        "report_schema_version": "1.0.0",
        "isa_level": "unknown",
        "verified_on": "2026-11-26",
        "verified_by": "автори проєкту",
        "verified_functions": [
            {
                "name": "graphics",
                "status": "pass",
                "evidence": ["artifacts/functional-test.log"],
            }
        ],
        "known_limitations": ["fixture only; not hardware support evidence"],
        "not_assessed": ["suspend/resume"],
        "artifacts": [
            {
                "kind": "wsm-hwcheck-report",
                "path": "artifacts/wsm-hwcheck-report.json",
                "sha256": digest(report_bytes),
            },
            {
                "kind": "functional-test-log",
                "path": "artifacts/functional-test.log",
                "sha256": digest(log_bytes),
            },
        ],
        "profile_source": {
            "path": "profile.scm",
            "sha256": digest(profile_bytes),
        },
    }


class ProfileEvidenceVersionTests(unittest.TestCase):
    def test_current_version_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = profile_bundle(root)
            self.assertEqual(profile.problems(document, artifact_root=root), [])

    def test_next_version_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = profile_bundle(root)
            document["schema"] = "wsm-profile-evidence/3"
            found = profile.problems(document, artifact_root=root)
        self.assertTrue(found, "a /3 bundle must not validate as /2")
        self.assertTrue(
            any("wsm-profile-evidence/3" in item for item in found),
            f"refusal must name the version it saw: {found}",
        )

    def test_missing_version_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = profile_bundle(root)
            del document["schema"]
            found = profile.problems(document, artifact_root=root)
        self.assertTrue(any("schema-version" in item for item in found), found)


class HardwareReportVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def report(self, version: str) -> Path:
        path = self.directory / f"report-{version}.json"
        path.write_text(
            json.dumps({"schema_version": version, "devices": []}),
            encoding="utf-8",
        )
        return path

    def test_current_version_is_accepted(self) -> None:
        criterion = preflight_env.check_report(self.report("1.0.0"))
        self.assertEqual(criterion["status"], "pass")

    def test_next_version_is_refused_by_name(self) -> None:
        criterion = preflight_env.check_report(self.report("1.1.0"))
        self.assertEqual(criterion["status"], "fail")
        self.assertIn("1.1.0", criterion["detail"])


class ReleaseInfoVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "check_release_info", ROOT / "scripts" / "check_release_info.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.checker = module
        self.document = json.loads(
            (ROOT / "RELEASE-INFO.json").read_text(encoding="utf-8")
        )

    def test_current_version_is_accepted(self) -> None:
        self.assertEqual(self.checker.problems(self.document), [])

    def test_next_version_is_refused_by_name(self) -> None:
        document = dict(self.document)
        document["schema"] = "wsm-release-info/2"
        found = self.checker.problems(document)
        self.assertTrue(
            any("wsm-release-info/2" in item for item in found),
            found,
        )


class ClassificationVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_classification", ROOT / "scripts" / "check_classification.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.checker = module
        from wsm_install.classification import classify

        self.document = classify({"devices": []})

    def test_current_version_is_accepted(self) -> None:
        self.assertEqual(self.checker.problems(self.document), [])

    def test_next_version_is_refused_by_name(self) -> None:
        document = copy.deepcopy(self.document)
        major, _, minor = document["schema"].rpartition("/")
        future = f"{major}/{int(minor) + 1}"
        document["schema"] = future
        found = self.checker.problems(document)
        self.assertTrue(any(future in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
