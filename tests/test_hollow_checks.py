# SPDX-License-Identifier: LicenseRef-Volnist
"""Three checks that could not fail, and now either work or say they cannot."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_gate import check_image  # noqa: E402
from verify_live_release import join_parts  # noqa: E402


class JoinPartsTests(unittest.TestCase):
    def make(self, directory: Path, payload: bytes, size: int) -> list[Path]:
        image = directory / "live.iso"
        image.write_bytes(payload)
        subprocess.run(
            ["split", "-b", str(size), "-d", "-a", "3", str(image), str(image) + ".part"],
            check=True,
        )
        image.unlink()
        return sorted(directory.glob("*.iso.part*"))

    def test_a_contiguous_set_joins_into_the_same_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            payload = bytes(range(256)) * 32
            parts = self.make(directory, payload, 2048)
            joined = join_parts(parts, directory / "joined.iso")
            self.assertEqual(joined.read_bytes(), payload)

    def test_a_gap_is_rejected(self) -> None:
        """part000 + part002 concatenates into a corrupt image of plausible size."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            parts = self.make(directory, b"x" * 4096, 1024)
            parts[1].unlink()
            remaining = [item for item in parts if item.exists()]
            with self.assertRaises(ValueError) as caught:
                join_parts(remaining, directory / "joined.iso")
            self.assertIn("contiguous", str(caught.exception))

    def test_mixed_zero_padding_is_rejected(self) -> None:
        """part0 and part001 sort into the wrong order under a plain sort."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "live.iso.part0").write_bytes(b"a")
            (directory / "live.iso.part001").write_bytes(b"b")
            with self.assertRaises(ValueError) as caught:
                join_parts(sorted(directory.glob("*.iso.part*")), directory / "joined.iso")
            self.assertIn("padding", str(caught.exception))


class PartsGateTests(unittest.TestCase):
    """A criterion that cannot be decided must say so, not report pass."""

    def test_parts_mode_reports_not_run_rather_than_a_self_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "live.iso.part000"
            part.write_bytes(b"first part")
            payload = {
                "schema": "wsm-release-verdict/1",
                "artifact": "live.iso",
                "artifact_source": "parts (2)",
                "artifact_sha256": hashlib.sha256(b"joined").hexdigest(),
                "overall": "pass",
                "criteria": [],
            }
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            )
            with patch("release_gate.subprocess.run", return_value=completed):
                result = check_image(part, boot=False)
        self.assertEqual(result["status"], "not-run")
        self.assertIn("parts", result["detail"])


class ReassembledNameTests(unittest.TestCase):
    """The joined file must carry the published name, or lookups miss."""

    def test_the_joined_file_is_named_like_the_artifact(self) -> None:
        source = (ROOT / "scripts" / "verify_live_release.py").read_text(encoding="utf-8")
        self.assertIn("reassembled = iso.parent / artifact_name", source)
        self.assertNotIn('"reassembled.iso"', source)


if __name__ == "__main__":
    unittest.main()
