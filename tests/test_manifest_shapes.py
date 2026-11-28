"""Both manifest shapes must be readable; the pipeline's own shape first."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_live_release import check_manifest, manifest_artifact  # noqa: E402


class ManifestShapeTests(unittest.TestCase):
    """The tool that decides "verified" must be able to read the evidence."""

    def write(self, directory: Path, payload: bytes) -> Path:
        iso = directory / "WSM-Desktop-test.iso"
        iso.write_bytes(payload)
        return iso

    def test_live_release_shape_is_understood(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            iso = self.write(directory, b"x" * 64)
            manifest = {
                "schema": "wsm-live-release/1",
                "artifact": {
                    "filename": iso.name,
                    "sha256": "a" * 64,
                    "bytes": 64,
                    "published_as": "whole",
                },
            }
            entry = manifest_artifact(iso, manifest)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], iso.name)
        self.assertEqual(entry["bytes"], 64)

    def test_legacy_list_shape_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            iso = self.write(directory, b"x" * 8)
            manifest = {"files": [{"name": iso.name, "sha256": "b" * 64}]}
            entry = manifest_artifact(iso, manifest)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["sha256"], "b" * 64)

    def test_a_truncated_file_fails_on_size(self) -> None:
        """A download can keep a matching prefix but not the length."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            iso = self.write(directory, b"x" * 10)
            manifest = {
                "schema": "wsm-live-release/1",
                "artifact": {"filename": iso.name, "sha256": "c" * 64, "bytes": 999},
            }
            result = check_manifest(iso, manifest, {iso.name: "c" * 64})
        self.assertEqual(result["status"], "fail")
        self.assertIn("bytes", result["detail"])

    def test_a_matching_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            iso = self.write(directory, b"y" * 32)
            manifest = {
                "schema": "wsm-live-release/1",
                "artifact": {"filename": iso.name, "sha256": "d" * 64, "bytes": 32},
            }
            result = check_manifest(iso, manifest, {iso.name: "d" * 64})
        self.assertEqual(result["status"], "pass")

    def test_an_unknown_name_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            iso = self.write(directory, b"z" * 4)
            manifest = {
                "schema": "wsm-live-release/1",
                "artifact": {"filename": "other.iso", "sha256": "e" * 64, "bytes": 4},
            }
            result = check_manifest(iso, manifest, {iso.name: "e" * 64})
        self.assertEqual(result["status"], "fail")
        self.assertIn("not described", result["detail"])


if __name__ == "__main__":
    unittest.main()
