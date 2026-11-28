# SPDX-License-Identifier: LicenseRef-Volnist
"""The FPC evidence reader must refuse what the Python reader refuses."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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

    def test_path_traversal_and_artifact_root_are_rejected(self) -> None:
        self.assertIn("escapes the bundle directory", self.pas)
        self.assertIn("is not a safe relative path", self.pas)
        self.assertIn("path must be stored under artifacts/", self.pas)
        self.assertIn("profile_source: source file does not exist", self.pas)

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
        self.assertIn("Output.Add('digest_verification', 'delegated')", self.pas)

    def test_it_never_writes_or_executes(self) -> None:
        for forbidden in ("Rewrite(", "fpOpen", "ExecuteProcess", "popen", "Shell("):
            self.assertNotIn(forbidden, self.pas, f"side effect present: {forbidden}")

    def test_a_failed_bundle_exits_non_zero(self) -> None:
        self.assertIn("Halt(5)", self.pas)

    def test_it_uses_the_bundled_json_unit_only(self) -> None:
        self.assertIn("fpjson", self.pas)
        for marker in ("synapse", "superobject", "lazjson"):
            self.assertNotIn(marker, self.pas)


@unittest.skipUnless(
    (shutil.which("fpc") and shutil.which("make")) or os.environ.get("WSM_PROFILE_FPC_BINARY"),
    "FPC is not installed; native profile reader runtime is not proven locally",
)
class RuntimeProfileReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("WSM_PROFILE_FPC_BINARY")
        cls.temporary = None
        if supplied:
            candidate = Path(supplied)
            cls.program = candidate if candidate.is_absolute() else ROOT / candidate
            if not cls.program.is_file():
                raise AssertionError(f"FPC profile binary does not exist: {cls.program}")
            return

        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-profile-")
        build_dir = Path(cls.temporary.name) / "build"
        completed = subprocess.run(
            ["make", "-C", str(ROOT / "tools" / "pascal"),
             f"BUILD_DIR={build_dir}", "wsm-profile"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "FPC profile build failed.\\n"
                f"stdout:\\n{completed.stdout}\\nstderr:\\n{completed.stderr}"
            )
        cls.program = build_dir / "wsm-profile"
        if not cls.program.is_file():
            raise AssertionError("FPC Makefile did not produce wsm-profile")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.temporary is not None:
            cls.temporary.cleanup()

    def run_reader(
        self,
        document: dict,
        *,
        artifact_files: tuple[str, ...] = (),
        include_profile_source: bool = True,
    ) -> tuple[int, dict]:
        root = Path(tempfile.mkdtemp(prefix="wsm-profile-case-"))
        if include_profile_source:
            (root / "profile.scm").write_text("(profile test)", encoding="utf-8")
        for relative in artifact_files:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("functional evidence\\n", encoding="utf-8")
        evidence = root / "evidence.json"
        evidence.write_text(json.dumps(document), encoding="utf-8")
        try:
            completed = subprocess.run(
                [str(self.program), str(evidence)],
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(completed.stdout)
            return completed.returncode, payload
        finally:
            shutil.rmtree(root)

    @staticmethod
    def valid_document() -> dict:
        return {
            "schema": "wsm-profile-evidence/2",
            "profile_source": {"path": "profile.scm"},
            "verified_functions": [{"name": "boot", "status": "pass"}],
            "artifacts": [{"path": "artifacts/boot.log"}],
        }

    def test_valid_bundle_is_accepted_and_digest_boundary_is_explicit(self) -> None:
        code, payload = self.run_reader(
            self.valid_document(), artifact_files=("artifacts/boot.log",)
        )
        self.assertEqual(code, 0)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["digest_verification"], "delegated")
        self.assertEqual(payload["problems"], [])

    def test_traversal_in_profile_source_is_rejected(self) -> None:
        document = self.valid_document()
        document["profile_source"]["path"] = "../outside/profile.scm"
        code, payload = self.run_reader(document, artifact_files=("artifacts/boot.log",))
        self.assertEqual(code, 5)
        self.assertIs(payload["ok"], False)
        self.assertIn("not a safe relative path", payload["problems"][0])

    def test_noncanonical_and_platform_specific_paths_are_rejected(self) -> None:
        for path in ("./profile.scm", "sub//profile.scm", "sub/profile.scm/",
                     r"sub\\profile.scm", "C:profile.scm"):
            with self.subTest(path=path):
                document = self.valid_document()
                document["profile_source"]["path"] = path
                code, payload = self.run_reader(
                    document, artifact_files=("artifacts/boot.log",)
                )
                self.assertEqual(code, 5)
                self.assertIs(payload["ok"], False)

    def test_missing_artifact_is_rejected(self) -> None:
        code, payload = self.run_reader(self.valid_document())
        self.assertEqual(code, 5)
        self.assertIs(payload["ok"], False)
        self.assertTrue(any("does not exist" in issue for issue in payload["problems"]))

    def test_artifacts_must_be_stored_under_artifacts_directory(self) -> None:
        document = self.valid_document()
        document["artifacts"][0]["path"] = "boot.log"
        code, payload = self.run_reader(document, artifact_files=("boot.log",))
        self.assertEqual(code, 5)
        self.assertTrue(any("stored under artifacts/" in issue for issue in payload["problems"]))

    def test_missing_profile_source_is_rejected(self) -> None:
        code, payload = self.run_reader(
            self.valid_document(),
            artifact_files=("artifacts/boot.log",),
            include_profile_source=False,
        )
        self.assertEqual(code, 5)
        self.assertTrue(any("profile_source: source file does not exist" in issue for issue in payload["problems"]))

    def test_bundle_without_a_passing_function_is_rejected(self) -> None:
        document = self.valid_document()
        document["verified_functions"] = [{"name": "boot", "status": "not-assessed"}]
        code, payload = self.run_reader(
            document, artifact_files=("artifacts/boot.log",)
        )
        self.assertEqual(code, 5)
        self.assertIs(payload["ok"], False)
        self.assertTrue(any("no function passed" in issue for issue in payload["problems"]))



if __name__ == "__main__":
    unittest.main()
