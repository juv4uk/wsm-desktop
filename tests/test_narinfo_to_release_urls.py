# SPDX-License-Identifier: LicenseRef-Volnist
"""Rewriting the archive URL must not touch anything the signature covers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from narinfo_to_release_urls import (  # noqa: E402
    convert_directory,
    rewrite_url,
    signed_fingerprint_fields,
)

NARINFO = """StorePath: /gnu/store/8bjy9g0cssjrw9ljz2r8ww1sma95isfj-wsm-tools-0.2.0
URL: nar/1z9k4m2q0x8v3n7p5r6t1y2u3i4o5a6s7d8f9g0h1j2k3l4m5n6o7p8q9r0s.nar.zst
Compression: zstd
FileHash: sha256:1z9k4m2q0x8v3n7p5r6t1y2u3i4o5a6s7d8f9g0h1j2k3l4m5n6o7p8q9r0s
FileSize: 4194304
NarHash: sha256:0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9
NarSize: 8388608
References: 5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d-wsm-tools-0.2.0
Sig: 1;example-key;AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==
"""


class RewriteTests(unittest.TestCase):
    def test_the_url_points_at_the_release_asset(self) -> None:
        result = rewrite_url(NARINFO, "https://example.invalid/releases/download/substitutes")
        self.assertIn("URL: https://example.invalid/releases/download/substitutes/1z9k4m2q", result)
        self.assertNotIn("URL: nar/", result)

    def test_the_nar_prefix_can_be_kept(self) -> None:
        result = rewrite_url(NARINFO, "https://example.invalid/c", keep_path=True)
        self.assertIn("/c/nar/1z9k4m2q", result)

    def test_the_signature_and_hashes_are_untouched(self) -> None:
        """The fingerprint covers path, NarHash, NarSize and References."""
        result = rewrite_url(NARINFO, "https://example.invalid/x")
        self.assertEqual(signed_fingerprint_fields(NARINFO), signed_fingerprint_fields(result))
        self.assertIn("Sig: 1;example-key;", result)

    def test_a_narinfo_without_a_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rewrite_url("StorePath: /gnu/store/x\n", "https://example.invalid")

    def test_every_narinfo_in_a_tree_is_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            (source / "sub").mkdir(parents=True)
            (source / "a.narinfo").write_text(NARINFO, encoding="utf-8")
            (source / "sub" / "b.narinfo").write_text(NARINFO, encoding="utf-8")
            destination = Path(tmp) / "out"
            written = convert_directory(source, destination, "https://example.invalid/c")
            self.assertEqual(len(written), 2)
            for path in written:
                self.assertIn("https://example.invalid/c/", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
