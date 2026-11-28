# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime tests for the native FPC evidence bundle validator."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    ROOT / "build" / "fpc" / "wsm_profile",
    ROOT / "build" / "pascal" / "wsm-profile",
)
BINARY = (
    Path(os.environ["WSM_FPC_PROFILE_BINARY"])
    if os.environ.get("WSM_FPC_PROFILE_BINARY")
    else next((p for p in CANDIDATES if p.is_file()), CANDIDATES[0])
)


@unittest.skipUnless(BINARY.is_file(), "the FPC workflow compiles wsm_profile")
class ProfileRuntimeTests(unittest.TestCase):
    def invoke(self, document: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return subprocess.run(
                [str(BINARY), str(path)], capture_output=True, text=True, check=False
            )

    def valid_document(self) -> dict:
        return {
            "schema": "wsm-profile-evidence/2",
            "verified_functions": [{"status": "pass"}],
            "artifacts": [],
        }

    def test_valid_bundle_emits_machine_readable_json(self) -> None:
        result = self.invoke(self.valid_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIs(output["ok"], True)
        self.assertEqual(output["digest_verification"], "delegated")
        self.assertEqual(output["problems"], [])

    def test_path_traversal_is_refused_and_json_escaped(self) -> None:
        document = self.valid_document()
        document["artifacts"] = [{"path": "nested/../bad\"quote"}]
        result = self.invoke(document)
        self.assertEqual(result.returncode, 5)
        output = json.loads(result.stdout)
        self.assertIs(output["ok"], False)
        self.assertIn("escapes the bundle directory", output["problems"][0])

    def test_missing_passing_function_is_refused(self) -> None:
        document = self.valid_document()
        document["verified_functions"] = [{"status": "not-assessed"}]
        result = self.invoke(document)
        self.assertEqual(result.returncode, 5)
        output = json.loads(result.stdout)
        self.assertIs(output["ok"], False)
        self.assertIn("no function passed", output["problems"][0])


if __name__ == "__main__":
    unittest.main()
