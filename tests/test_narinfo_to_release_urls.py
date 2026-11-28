# SPDX-License-Identifier: LicenseRef-Volnist
"""URL rewriting must preserve the complete Guix-signed narinfo payload."""

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
    signed_prefix,
)

# Layout follows pinned Guix publish.scm: the signed payload ends at Signature;
# URL, Compression and FileSize are rendered afterwards.
NARINFO = """StorePath: /gnu/store/8bjy9g0cssjrw9ljz2r8ww1sma95isfj-wsm-tools-0.2.0
NarHash: sha256:0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9
NarSize: 8388608
References: 5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d-wsm-tools-0.2.0
Deriver: 9z8y7x6w5v4u3t2s1r0q-wsm-tools.drv
Signature: 1;build-host;AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==
URL: nar/gzip/1z9k4m2q0x8v3n7p5r6t1y2u3i4o5a6s7d8f9g0h1j2k3l4m5n6o7p8q9r0s
Compression: gzip
FileSize: 4194304
"""


class RewriteTests(unittest.TestCase):
    def test_rewrites_only_the_url_value(self) -> None:
        base = "https://example.invalid/releases/download/substitutes"
        target = "1z9k4m2q0x8v3n7p5r6t1y2u3i4o5a6s7d8f9g0h1j2k3l4m5n6o7p8q9r0s"
        result = rewrite_url(NARINFO, base)
        expected = NARINFO.replace(
            f"URL: nar/gzip/{target}",
            f"URL: {base}/{target}",
        )
        self.assertEqual(result, expected)
        self.assertEqual(signed_prefix(result), signed_prefix(NARINFO))

    def test_keep_path_preserves_compression_subdirectory(self) -> None:
        result = rewrite_url(NARINFO, "https://example.invalid/cache", keep_path=True)
        self.assertIn("URL: https://example.invalid/cache/nar/gzip/", result)

    def test_signature_and_every_signed_byte_are_unchanged(self) -> None:
        result = rewrite_url(NARINFO, "https://example.invalid/cache")
        self.assertEqual(signed_prefix(result), signed_prefix(NARINFO))
        self.assertIn("Signature: 1;build-host;", result)
        self.assertNotIn("Sig:", result)

    def test_requires_exactly_one_url_and_signature(self) -> None:
        with self.assertRaisesRegex(ValueError, "Signature"):
            rewrite_url(NARINFO.replace("Signature:", "Sig:"), "https://example.invalid")
        with self.assertRaisesRegex(ValueError, "exactly one URL"):
            rewrite_url(NARINFO + "URL: nar/gzip/second\n", "https://example.invalid")

    def test_url_must_follow_signature(self) -> None:
        url_line = next(line for line in NARINFO.splitlines(keepends=True) if line.startswith("URL:"))
        altered = NARINFO.replace(url_line, "")
        signature_pos = altered.index("Signature:")
        altered = altered[:signature_pos] + url_line + altered[signature_pos:]
        with self.assertRaisesRegex(ValueError, "follow the signed Signature"):
            rewrite_url(altered, "https://example.invalid")

    def test_base_url_must_be_absolute_http_or_https(self) -> None:
        for base in ("relative/path", "ftp://example.invalid/cache", "https://example.invalid/cache?q=x"):
            with self.subTest(base=base), self.assertRaisesRegex(ValueError, "absolute HTTP"):
                rewrite_url(NARINFO, base)

    def test_batch_conversion_forwards_keep_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "item.narinfo").write_text(NARINFO, encoding="utf-8")
            destination = Path(tmp) / "out"
            written = convert_directory(
                source, destination, "https://example.invalid/cache", keep_path=True
            )
            self.assertEqual(len(written), 1)
            self.assertIn(
                "URL: https://example.invalid/cache/nar/gzip/",
                written[0].read_text(encoding="utf-8"),
            )

    def test_missing_source_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaisesRegex(ValueError, "source directory does not exist"):
                convert_directory(missing, Path(tmp) / "out", "https://example.invalid")


if __name__ == "__main__":
    unittest.main()
