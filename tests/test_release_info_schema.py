# SPDX-License-Identifier: LicenseRef-Volnist
"""Release metadata must refuse to describe a release it cannot describe.

Each test breaks exactly one promise the file makes and asserts that the
validator notices. A schema that only passes is not a schema; it is a
formality.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_info.py"
RELEASE_INFO = ROOT / "RELEASE-INFO.json"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_release_info", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()
BASELINE = json.loads(RELEASE_INFO.read_text(encoding="utf-8"))


class ReleaseInfoSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = copy.deepcopy(BASELINE)

    def problems(self) -> list[str]:
        return checker.problems(self.document)

    def test_repository_metadata_is_valid(self) -> None:
        self.assertEqual(checker.problems(BASELINE), [])

    def test_unknown_schema_version_is_refused(self) -> None:
        self.document["schema"] = "wsm-release-info/2"
        found = self.problems()
        self.assertTrue(any("schema-version" in item for item in found), found)

    def test_missing_required_field_is_refused(self) -> None:
        del self.document["excluded"]
        found = self.problems()
        self.assertTrue(any("excluded" in item for item in found), found)

    def test_unknown_field_is_refused(self) -> None:
        self.document["installer_apply"] = "enabled"
        found = self.problems()
        self.assertTrue(any("installer_apply" in item for item in found), found)

    def test_status_comes_from_the_closed_vocabulary(self) -> None:
        self.document["status"] = "beta-ish"
        found = self.problems()
        self.assertTrue(any("status" in item for item in found), found)

    def test_date_must_be_iso(self) -> None:
        self.document["date"] = "26.11.2026"
        found = self.problems()
        self.assertTrue(any("date" in item for item in found), found)

    def test_artifact_must_be_a_bare_file_name(self) -> None:
        self.document["artifacts"] = list(self.document["artifacts"]) + ["../outside.tar.gz"]
        found = self.problems()
        self.assertTrue(any("artifact-path" in item for item in found), found)

    def test_version_must_appear_in_an_artifact_name(self) -> None:
        self.document["artifacts"] = ["SHA256SUMS", "release-manifest.json"]
        found = self.problems()
        self.assertTrue(any("version" in item for item in found), found)

    def test_empty_exclusion_list_claims_completeness(self) -> None:
        self.document["excluded"] = []
        found = self.problems()
        self.assertTrue(any("excluded" in item for item in found), found)

    def test_scope_must_say_something(self) -> None:
        self.document["scope"] = ["ok"]
        found = self.problems()
        self.assertTrue(any("scope" in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
