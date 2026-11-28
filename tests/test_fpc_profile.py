# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC evidence reader must refuse what the Python reader refuses."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "pascal" / "wsm_profile.pas"
PY = ROOT / "wsm_install" / "profile.py"


class SemanticParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")
        self.py = PY.read_text(encoding="utf-8")

    def test_the_supported_schema_matches(self) -> None:
        self.assertIn("'wsm-profile-evidence/2'", self.pas)
        self.assertIn('"wsm-profile-evidence/2"', self.py)

    def test_an_unknown_version_is_refused_not_upgraded(self) -> None:
        self.assertIn("does not upgrade an unknown bundle version", self.pas)

    def test_path_traversal_is_rejected(self) -> None:
        self.assertIn("escapes the bundle directory", self.pas)
        self.assertIn("is not a safe relative path", self.pas)

    def test_a_bundle_without_a_passing_function_is_refused(self) -> None:
        self.assertIn("hypothesis, not evidence", self.pas)

    def test_duplicate_artifact_paths_are_refused(self) -> None:
        self.assertIn("duplicate artifact path", self.pas)

    def test_a_missing_artifact_is_refused(self) -> None:
        self.assertIn("does not exist under the bundle directory", self.pas)


class HonestBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pas = SRC.read_text(encoding="utf-8")

    def test_digest_verification_is_declared_as_delegated(self) -> None:
        """Shipping an unverified SHA-256 would be worse than delegating."""
        self.assertIn('"digest_verification":"delegated"', self.pas)

    def test_it_never_writes_or_executes(self) -> None:
        for forbidden in ("Rewrite(", "fpOpen", "ExecuteProcess", "popen", "Shell("):
            self.assertNotIn(forbidden, self.pas, f"side effect present: {forbidden}")

    def test_a_failed_bundle_exits_non_zero(self) -> None:
        self.assertIn("Halt(5)", self.pas)

    def test_it_uses_the_bundled_json_unit_only(self) -> None:
        self.assertIn("fpjson", self.pas)
        for marker in ("synapse", "superobject", "lazjson"):
            self.assertNotIn(marker, self.pas)


if __name__ == "__main__":
    unittest.main()
