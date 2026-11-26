# SPDX-License-Identifier: LicenseRef-Volnist
"""Every reader must refuse an artifact version it does not know.

`docs/LESSONS-FROM-OMARCHY.md` states the rule: each artifact carries a schema
version, and a reader refuses an unknown one instead of guessing. The rule was
true per artifact but never tested across them, so a reader could quietly start
accepting a future version and nothing would notice.

The tests derive the expected version from the schema itself. That way bumping
`wsm-profile-evidence/2` to `/3` does not leave this file asserting yesterday's
number: it keeps testing the property, not the constant.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install import preflight_env, profile  # noqa: E402

PROFILE_SCHEMA = ROOT / "schemas" / "profile-evidence.schema.json"


def expected_profile_version() -> str:
    schema = json.loads(PROFILE_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["schema"]["const"]


def bump(version: str) -> str:
    """`wsm-profile-evidence/2` -> `wsm-profile-evidence/3`."""
    match = re.fullmatch(r"(.*/)(\d+)", version)
    assert match, f"unexpected version shape: {version!r}"
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def bundle() -> dict:
    """A profile evidence bundle that is valid except for the version."""
    document = json.loads(
        (ROOT / "profiles" / "hardware" / "template.json").read_text(encoding="utf-8")
    )
    document["verified_functions"] = [
        {"name": "graphics", "status": "pass", "note": "fixture"},
        {"name": "storage", "status": "not-assessed"},
    ]
    document["known_limitations"] = ["fixture"]

    return document


class ProfileEvidenceVersionTests(unittest.TestCase):
    def test_current_version_is_not_refused_for_its_version(self) -> None:
        """The reader may still want an evidence directory; the version is fine."""
        found = profile.problems(bundle())
        self.assertFalse(
            [item for item in found if item.startswith("schema-version:")],
            f"a current-version bundle must not be refused for its version: {found}",
        )

    def test_next_version_is_refused_by_name(self) -> None:
        document = bundle()
        future = bump(expected_profile_version())
        document["schema"] = future
        found = profile.problems(document)
        self.assertTrue(found, "a future bundle version must not validate")
        self.assertTrue(
            any(future in item for item in found),
            f"refusal must name the version it saw: {found}",
        )

    def test_missing_version_is_refused_by_name(self) -> None:
        document = bundle()
        del document["schema"]
        found = profile.problems(document)
        self.assertTrue(any("schema-version" in item for item in found), found)


class HardwareReportVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def report(self, version: str) -> Path:
        path = self.directory / f"report-{version}.json"
        path.write_text(json.dumps({"schema_version": version, "devices": []}), encoding="utf-8")
        return path

    def test_current_version_is_accepted(self) -> None:
        self.assertEqual(preflight_env.check_report(self.report("1.0.0"))["status"], "pass")

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
        self.document = json.loads((ROOT / "RELEASE-INFO.json").read_text(encoding="utf-8"))

    def test_current_version_is_accepted(self) -> None:
        self.assertEqual(self.checker.problems(self.document), [])

    def test_next_version_is_refused_by_name(self) -> None:
        document = copy.deepcopy(self.document)
        document["schema"] = bump(self.document["schema"])
        found = self.checker.problems(document)
        self.assertTrue(any(document["schema"] in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
