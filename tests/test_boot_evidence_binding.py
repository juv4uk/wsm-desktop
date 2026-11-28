# SPDX-License-Identifier: LicenseRef-Volnist
"""Boot evidence must name the image it came from, not just "an image"."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qemu_boot_smoke import main, sha256_of  # noqa: E402


class BootEvidenceBindingTests(unittest.TestCase):
    def test_the_hash_matches_a_known_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_of(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_the_hash_is_streamed_not_loaded_whole(self) -> None:
        """A 1 GiB ISO must not be read into memory."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.bin"
            path.write_bytes(b"\0" * (3 * 1024 * 1024 + 7))
            self.assertEqual(len(sha256_of(path)), 64)

    def test_the_dry_run_reports_the_hash_it_would_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "live.iso"
            iso.write_bytes(b"placeholder")
            result = main(["--iso", str(iso), "--dry-run"])
        self.assertEqual(result, 0)

    def test_the_workflow_refuses_evidence_from_another_image(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-minimal-live.yml").read_text(encoding="utf-8")
        self.assertIn('evidence.get("iso_sha256") != iso_sha', workflow)
        self.assertIn("produced from a different image", workflow)

    def test_the_harness_records_the_digest(self) -> None:
        source = (ROOT / "scripts" / "qemu_boot_smoke.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('"iso_sha256"'), 2)


if __name__ == "__main__":
    unittest.main()
