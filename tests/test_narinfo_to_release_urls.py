# SPDX-License-Identifier: LicenseRef-Volnist
"""Rewriting a Guix narinfo may change only its URL value."""

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
)

STORE_BASENAME = "8bjy9g0cssjrw9ljz2r8ww1sma95isfj-wsm-tools-0.2.0"
NARINFO = f"""StorePath: /gnu/store/{STORE_BASENAME}
URL: nar/gzip/{STORE_BASENAME}
Compression: gzip
FileHash: sha256:1z9k4m2q0x8v3n7p5r6t1y2u3i4o5a6s7d8f9g0h1j2k3l4m5n6o7p8q9r0s
FileSize: 4194304
NarHash: sha256:0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9
NarSize: 8388608
References: 5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d-wsm-tools-0.2.0
Deriver: 4a5b6c7d8e9f0a1b2c3d4e5f607182934a5b6c7d8e9f0a1b2c3d4e5f60718293-wsm-tools-0.2.0.drv
Signature: 1;wsm-cache;AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==
"""


class RewriteTests(unittest.TestCase):
    def test_url_points_at_the_actual_release_asset_filename(self) -> None:
        result = rewrite_url(
            NARINFO,
            "https://github.com/example/wsm/releases/download/cache-v1",
        )
        expected = (
            "URL: https://github.com/example/wsm/releases/download/"
            f"cache-v1/{STORE_BASENAME}.nar"
        )
        self.assertIn(expected, result)
        self.assertIn("Compression: gzip\n", result)

    def test_only_the_url_value_changes_byte_for_byte(self) -> None:
        result = rewrite_url(NARINFO, "https://example.invalid/releases/cache")
        original_url = f"nar/gzip/{STORE_BASENAME}"
        rewritten_url = (
            "https://example.invalid/releases/cache/"
            f"{STORE_BASENAME}.nar"
        )
        self.assertEqual(
            NARINFO.replace(f"URL: {original_url}", f"URL: {rewritten_url}"),
            result,
        )
        self.assertIn("StorePath:", result)
        self.assertIn("NarHash:", result)
        self.assertIn("NarSize:", result)
        self.assertIn("References:", result)
        self.assertIn("Deriver:", result)
        self.assertIn("Signature: 1;wsm-cache;", result)

    def test_a_missing_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one URL"):
            rewrite_url("StorePath: /gnu/store/x\n", "https://example.invalid")

    def test_duplicate_url_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "found 2"):
            rewrite_url(
                "URL: nar/gzip/a\nURL: nar/gzip/b\n",
                "https://example.invalid",
            )

    def test_unsafe_empty_nar_basename_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no usable NAR basename"):
            rewrite_url("URL: nar/gzip/\n", "https://example.invalid")

    def test_cache_subdirectories_are_flattened_for_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cache"
            (source / "gzip").mkdir(parents=True)
            (source / "gzip" / f"{STORE_BASENAME}.narinfo").write_text(
                NARINFO, encoding="utf-8"
            )
            destination = Path(tmp) / "pages"
            written = convert_directory(
                source, destination, "https://example.invalid/release"
            )

            self.assertEqual(len(written), 1)
            self.assertEqual(written[0].name, f"{STORE_BASENAME}.narinfo")
            self.assertTrue(written[0].is_file())
            self.assertFalse((destination / "gzip").exists())

    def test_empty_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "empty"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, "no .narinfo files"):
                convert_directory(
                    source, Path(tmp) / "pages", "https://example.invalid"
                )


if __name__ == "__main__":
    unittest.main()
