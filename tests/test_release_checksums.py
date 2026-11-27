# SPDX-License-Identifier: LicenseRef-Volnist
"""The Minimal Live release manifest must describe both whole and split ISO uploads."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_release_checksums import (  # noqa: E402
    ReleaseManifestError,
    prepare_release_checksums,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_fixture(root: Path, published_as: str) -> tuple[Path, str, bytes]:
    root.mkdir()
    iso_name = "WSM-Desktop-test-Minimal-Live.iso"
    payload = b"minimal-live-image-" * 4096
    (root / "build-manifest.json").write_text('{"schema":"build/1"}\n', encoding="utf-8")
    (root / "boot-bios.json").write_text('{"boot_confirmed":true}\n', encoding="utf-8")
    (root / "boot-uefi.json").write_text('{"boot_confirmed":true}\n', encoding="utf-8")
    manifest = {
        "schema": "wsm-live-release/1",
        "artifact": {"filename": iso_name, "bytes": len(payload), "sha256": sha(payload)},
    }
    (root / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    if published_as == "whole":
        (root / iso_name).write_bytes(payload)
    else:
        midpoint = len(payload) // 2
        (root / f"{iso_name}.part000").write_bytes(payload[:midpoint])
        (root / f"{iso_name}.part001").write_bytes(payload[midpoint:])
    return root, iso_name, payload


def read_sums(path: Path) -> dict[str, str]:
    return {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
    }


class ReleaseChecksumPreparationTests(unittest.TestCase):
    def assert_top_manifest_covers_sidecar(self, root: Path) -> None:
        entries = read_sums(root / "SHA256SUMS")
        sidecar = root / "ISO-CHECKSUMS.sha256"
        self.assertIn(sidecar.name, entries)
        self.assertEqual(entries[sidecar.name], sha(sidecar.read_bytes()))
        for name, digest in entries.items():
            self.assertEqual(digest, sha((root / name).read_bytes()), name)

    def test_whole_iso_always_gets_iso_sidecar_and_top_level_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, iso_name, payload = write_fixture(Path(temporary) / "dist", "whole")
            result = prepare_release_checksums(root, iso_name, "whole")
            sidecar = (root / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
            self.assertEqual(sidecar, f"{sha(payload)}  {iso_name}\n")
            self.assertEqual(result["published_as"], "whole")
            self.assertEqual(result["asset_count"], 6)
            self.assert_top_manifest_covers_sidecar(root)
            release_manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(release_manifest["artifact"]["published_as"], "whole")

    def test_split_iso_sidecar_lists_every_part_and_top_level_covers_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, iso_name, payload = write_fixture(Path(temporary) / "dist", "parts")
            result = prepare_release_checksums(root, iso_name, "parts")
            parts = [f"{iso_name}.part000", f"{iso_name}.part001"]
            sidecar = (root / "ISO-CHECKSUMS.sha256").read_text(encoding="utf-8")
            expected = "".join(
                f"{sha((root / name).read_bytes())}  {name}\n" for name in parts
            )
            self.assertEqual(sidecar, expected)
            self.assertEqual(result["published_as"], "parts")
            self.assertEqual(result["asset_count"], 7)
            self.assertEqual(b"".join((root / name).read_bytes() for name in parts), payload)
            self.assert_top_manifest_covers_sidecar(root)
            release_manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(release_manifest["artifact"]["parts"], parts)
            self.assertEqual(release_manifest["artifact"]["parts_count"], 2)

    def test_split_parts_must_reconstruct_manifested_iso(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, iso_name, _payload = write_fixture(Path(temporary) / "dist", "parts")
            (root / f"{iso_name}.part001").write_bytes(b"corrupted tail")
            with self.assertRaisesRegex(ReleaseManifestError, "do not reconstruct"):
                prepare_release_checksums(root, iso_name, "parts")

    def test_whole_mode_rejects_stale_parts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, iso_name, _payload = write_fixture(Path(temporary) / "dist", "whole")
            (root / f"{iso_name}.part000").write_bytes(b"stale")
            with self.assertRaisesRegex(ReleaseManifestError, "stale split parts"):
                prepare_release_checksums(root, iso_name, "whole")

    def test_split_mode_requires_parts_and_removes_whole_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, iso_name, _payload = write_fixture(Path(temporary) / "dist", "whole")
            with self.assertRaisesRegex(ReleaseManifestError, "must not contain the unsplit"):
                prepare_release_checksums(root, iso_name, "parts")


if __name__ == "__main__":
    unittest.main()
