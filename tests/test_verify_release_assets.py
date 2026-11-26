# SPDX-License-Identifier: LicenseRef-Volnist
"""The remote release verifier must reject partial, changed and unsafe assets."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_release_assets import ReleaseAssetError, verify_release_assets  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_bundle(root: Path) -> tuple[Path, Path]:
    expected = root / "expected"
    downloaded = root / "downloaded"
    expected.mkdir()
    downloaded.mkdir()
    assets = {
        "wsm.iso": b"iso-image-bytes",
        "build-manifest.json": b'{"schema":"build/1"}\n',
        "release-manifest.json": b'{"schema":"release/1"}\n',
        "boot-bios.json": b'{"boot_confirmed":true}\n',
        "boot-uefi.json": b'{"boot_confirmed":true}\n',
    }
    for name, content in assets.items():
        (expected / name).write_bytes(content)
        (downloaded / name).write_bytes(content)
    sums = "".join(f"{digest(content)}  {name}\n" for name, content in sorted(assets.items()))
    (expected / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (downloaded / "SHA256SUMS").write_text(sums, encoding="utf-8")
    # Local notes are deliberately not release assets and are not listed.
    (expected / "RELEASE-NOTES.md").write_text("release notes", encoding="utf-8")
    return expected, downloaded


class ReleaseAssetVerificationTests(unittest.TestCase):
    def test_release_workflow_attests_every_asset_after_readback(self) -> None:
        import yaml

        workflow_path = ROOT / ".github" / "workflows" / "release-minimal-live.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        permissions = workflow["permissions"]
        for permission in ("contents", "id-token", "attestations", "artifact-metadata"):
            with self.subTest(permission=permission):
                self.assertEqual(permissions[permission], "write")

        steps = workflow["jobs"]["build-and-publish"]["steps"]
        names = [step.get("name", "") for step in steps]
        readback = names.index("Перевірити завантажені assets до публікації")
        attest_index = names.index("Підписати provenance релізних артефактів")
        verify_index = names.index("Перевірити provenance артефактів перед публікацією")
        publish = names.index("Опублікувати перевірений GitHub pre-release")
        self.assertLess(readback, attest_index)
        self.assertLess(attest_index, verify_index)
        self.assertLess(verify_index, publish)

        attest = steps[attest_index]
        self.assertEqual(attest["uses"], "actions/attest@v4")
        self.assertIs(attest["with"]["create-storage-record"], False)
        subjects = attest["with"]["subject-path"]
        for filename in (
            "WSM-Desktop-0.1.0-rc3-Minimal-Live.iso",
            "SHA256SUMS",
            "build-manifest.json",
            "release-manifest.json",
            "boot-bios.json",
            "boot-uefi.json",
        ):
            with self.subTest(subject=filename):
                self.assertIn(filename, subjects)

        verification = steps[verify_index]["run"]
        self.assertIn("gh attestation verify", verification)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', verification)
        self.assertIn("--bundle", verification)
        self.assertIn("--signer-workflow", verification)
        self.assertIn("release-minimal-live.yml", verification)
        self.assertIn("https://slsa.dev/provenance/v1", verification)

    def test_valid_download_matches_local_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            result = verify_release_assets(expected, downloaded)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["verified_asset_count"], 5)
        self.assertEqual(
            [item["name"] for item in result["assets"]],
            ["boot-bios.json", "boot-uefi.json", "build-manifest.json", "release-manifest.json", "wsm.iso"],
        )

    def test_changed_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "wsm.iso").write_bytes(b"truncated remote bytes")
            with self.assertRaisesRegex(ReleaseAssetError, "checksum mismatch"):
                verify_release_assets(expected, downloaded)

    def test_missing_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "boot-uefi.json").unlink()
            with self.assertRaisesRegex(ReleaseAssetError, "asset set differs"):
                verify_release_assets(expected, downloaded)

    def test_extra_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "unexpected.bin").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ReleaseAssetError, "asset set differs"):
                verify_release_assets(expected, downloaded)

    def test_checksum_manifest_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "SHA256SUMS").write_text("0" * 64 + "  wsm.iso\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseAssetError, "SHA256SUMS differs"):
                verify_release_assets(expected, downloaded)

    def test_path_traversal_in_checksum_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            sums = (expected / "SHA256SUMS").read_text(encoding="utf-8")
            (expected / "SHA256SUMS").write_text(sums + "0" * 64 + "  ../escape.bin\n", encoding="utf-8")
            (downloaded / "SHA256SUMS").write_text((expected / "SHA256SUMS").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseAssetError, "unsafe"):
                verify_release_assets(expected, downloaded)

    def test_symlink_in_download_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, downloaded = make_bundle(root)
            target = downloaded / "wsm.iso"
            target.unlink()
            target.symlink_to(expected / "wsm.iso")
            with self.assertRaisesRegex(ReleaseAssetError, "non-regular"):
                verify_release_assets(expected, downloaded)


if __name__ == "__main__":
    unittest.main()
