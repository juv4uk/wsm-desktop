# SPDX-License-Identifier: LicenseRef-Volnist
"""The final release bundle is ready only when all shipped evidence agrees."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_readiness", ROOT / "scripts" / "check_release_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def build(directory: Path, installer_executed: bool = True) -> None:
    boot = {
        "boot_confirmed": True,
        "guest_installer_execution": installer_executed,
        "serial_output_tail": "...WSM_LIVE_READY...WSM_INSTALLER_OK...",
    }
    bios_path = directory / "boot-bios.json"
    uefi_path = directory / "boot-uefi.json"
    write_json(bios_path, boot)
    write_json(uefi_path, boot)

    build_path = directory / "build-manifest.json"
    write_json(build_path, {"schema": "wsm-build/1", "source": {"commit": "test"}})

    image_path = directory / "image.iso"
    image_path.write_bytes(b"iso-image-bytes")
    manifest = {
        "acceptance": {
            "bios": "pass",
            "uefi": "pass",
            "installer": "pass",
            "marker": "WSM_LIVE_READY",
            "installer_marker": "WSM_INSTALLER_OK",
        },
        "artifact": {
            "filename": "image.iso",
            "bytes": image_path.stat().st_size,
            "sha256": checker.sha256_of(image_path),
            "published_as": "whole",
        },
        "boot_evidence": {
            "bios_sha256": checker.sha256_of(bios_path),
            "uefi_sha256": checker.sha256_of(uefi_path),
        },
        "build_manifest_sha256": checker.sha256_of(build_path),
    }
    write_json(directory / "release-manifest.json", manifest)
    write_sums(directory)


def write_sums(
    directory: Path,
    image_assets: tuple[str, ...] = ("image.iso",),
    extra: tuple[str, ...] = (),
) -> None:
    names = (
        *image_assets,
        "build-manifest.json",
        "release-manifest.json",
        "boot-bios.json",
        "boot-uefi.json",
        *extra,
    )
    lines = []
    for name in names:
        path = directory / name
        digest = checker.sha256_of(path) if path.is_file() else "0" * 64
        lines.append(f"{digest}  {name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rewrite_checksum(directory: Path, name: str) -> None:
    path = directory / name
    digest = checker.sha256_of(path)
    sums = directory / "SHA256SUMS"
    lines = sums.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.endswith(f"  {name}"):
            lines[index] = f"{digest}  {name}"
            replaced = True
    if not replaced:
        raise AssertionError(f"missing checksum entry for {name}")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_parts(directory: Path, first: bytes = b"iso-", second: bytes = b"image-bytes") -> None:
    image = directory / "image.iso"
    payload = image.read_bytes()
    manifest_path = directory / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    part_names = ("image.iso.part000", "image.iso.part001")
    (directory / part_names[0]).write_bytes(first)
    (directory / part_names[1]).write_bytes(second)
    manifest["artifact"]["published_as"] = "parts"
    manifest["artifact"]["parts"] = list(part_names)
    manifest["artifact"]["parts_count"] = len(part_names)
    # The caller may use deliberately incorrect contents to test the combined hash.
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    image.unlink()
    (directory / "ISO-CHECKSUMS.sha256").write_text(
        "".join(
            f"{checker.sha256_of(directory / name)}  {name}\n"
            for name in part_names
        ),
        encoding="utf-8",
    )
    write_sums(directory, image_assets=part_names, extra=("ISO-CHECKSUMS.sha256",))


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        build(self.directory)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_consistent_whole_iso_bundle_is_ready(self) -> None:
        self.assertEqual(checker.problems(self.directory), [])

    def test_installer_acceptance_without_execution_is_refused(self) -> None:
        build(self.directory, installer_executed=False)
        found = checker.problems(self.directory)
        self.assertTrue(any("guest_installer_execution false" in item for item in found), found)

    def test_installer_claim_without_serial_marker_is_refused(self) -> None:
        record_path = self.directory / "boot-bios.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["serial_output_tail"] = "WSM_LIVE_READY only"
        write_json(record_path, record)
        rewrite_checksum(self.directory, "boot-bios.json")
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = checker.sha256_of(record_path)
        write_json(manifest_path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("never showed WSM_INSTALLER_OK" in item for item in found), found)

    def test_missing_manifest_marker_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["marker"] = ""
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.marker is missing" in item for item in found), found)

    def test_missing_installer_marker_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["installer_marker"] = None
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.installer_marker is missing" in item for item in found), found)

    def test_missing_acceptance_pass_is_refused(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["acceptance"]["uefi"] = "unknown"
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("acceptance.uefi is not pass" in item for item in found), found)

    def test_a_missing_required_evidence_asset_is_refused(self) -> None:
        (self.directory / "boot-uefi.json").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("missing boot-uefi.json" in item for item in found), found)

    def test_a_missing_sha256sums_listed_asset_is_refused(self) -> None:
        write_sums(self.directory, extra=("build-metadata.json",))
        found = checker.problems(self.directory)
        self.assertTrue(
            any("build-metadata.json is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_a_corrupted_image_is_refused(self) -> None:
        (self.directory / "image.iso").write_bytes(b"tampered")
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso does not match its recorded hash" in item for item in found), found)

    def test_an_absent_image_is_not_ready_by_default(self) -> None:
        (self.directory / "image.iso").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso is listed in SHA256SUMS but is absent" in item for item in found), found)

    def test_metadata_only_is_explicitly_not_ready(self) -> None:
        (self.directory / "image.iso").unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = checker.main([str(self.directory), "--metadata-only"])
        self.assertEqual(result, 2)
        self.assertIn("NOT_READY", output.getvalue())

    def test_a_consistent_multipart_bundle_is_ready(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        self.assertEqual(checker.problems(self.directory), [])

    def test_a_missing_multipart_part_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "image.iso.part001").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(
            any("image.iso.part001 is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_missing_multipart_sidecar_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "ISO-CHECKSUMS.sha256").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(
            any("ISO-CHECKSUMS.sha256 is listed in SHA256SUMS but is absent" in item for item in found),
            found,
        )

    def test_multipart_sidecar_contents_are_verified(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        sidecar = self.directory / "ISO-CHECKSUMS.sha256"
        sidecar.write_text("0" * 64 + "  image.iso.part000\n", encoding="utf-8")
        rewrite_checksum(self.directory, "ISO-CHECKSUMS.sha256")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("ISO-CHECKSUMS.sha256 does not match" in item for item in found),
            found,
        )

    def test_extra_multipart_piece_is_refused(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        (self.directory / "image.iso.part002").write_bytes(b"extra")
        found = checker.problems(self.directory)
        self.assertTrue(any("unexpected split parts" in item for item in found), found)

    def test_multipart_part_numbers_must_be_contiguous(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        old_part = self.directory / "image.iso.part001"
        new_part = self.directory / "image.iso.part002"
        old_part.rename(new_part)
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifact"]["parts"][1] = new_part.name
        write_json(manifest_path, manifest)
        sidecar = self.directory / "ISO-CHECKSUMS.sha256"
        sidecar.write_text(
            "".join(
                f"{checker.sha256_of(self.directory / name)}  {name}\n"
                for name in manifest["artifact"]["parts"]
            ),
            encoding="utf-8",
        )
        write_sums(
            self.directory,
            image_assets=tuple(manifest["artifact"]["parts"]),
            extra=("ISO-CHECKSUMS.sha256",),
        )
        found = checker.problems(self.directory)
        self.assertTrue(any("not contiguously numbered" in item for item in found), found)

    def test_missing_build_manifest_checksum_row_is_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        lines = [
            line for line in sums.read_text(encoding="utf-8").splitlines()
            if not line.endswith("  build-manifest.json")
        ]
        sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("build-manifest.json is not listed" in item for item in found), found)

    def test_missing_boot_evidence_hash_fields_are_refused(self) -> None:
        for key in ("bios_sha256", "uefi_sha256"):
            with self.subTest(key=key):
                manifest_path = self.directory / "release-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["boot_evidence"].pop(key)
                write_json(manifest_path, manifest)
                rewrite_checksum(self.directory, "release-manifest.json")
                found = checker.problems(self.directory)
                self.assertTrue(any(f"boot_evidence.{key} is missing" in item for item in found), found)
                build(self.directory)

    def test_every_acceptance_state_is_mandatory(self) -> None:
        for key in ("bios", "uefi", "installer"):
            with self.subTest(key=key):
                manifest_path = self.directory / "release-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["acceptance"].pop(key)
                write_json(manifest_path, manifest)
                rewrite_checksum(self.directory, "release-manifest.json")
                found = checker.problems(self.directory)
                self.assertTrue(any(f"acceptance.{key} is not pass" in item for item in found), found)
                build(self.directory)

    def test_boot_json_whitespace_change_without_checksum_update_is_refused(self) -> None:
        path = self.directory / "boot-bios.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("boot-bios.json does not match its recorded hash" in item for item in found),
            found,
        )

    def test_multipart_contents_must_reconstruct_the_declared_iso(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], b"wrong")
        found = checker.problems(self.directory)
        self.assertTrue(
            any("concatenated artifact parts do not match" in item for item in found),
            found,
        )

    def test_multipart_parts_must_be_in_lexical_order(self) -> None:
        payload = (self.directory / "image.iso").read_bytes()
        make_parts(self.directory, payload[:4], payload[4:])
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifact"]["parts"].reverse()
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("not in lexical concatenation order" in item for item in found), found)

    def test_build_manifest_digest_must_match(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["build_manifest_sha256"] = "0" * 64
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("build_manifest_sha256" in item for item in found), found)

    def test_boot_evidence_digest_must_match(self) -> None:
        path = self.directory / "release-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["boot_evidence"]["bios_sha256"] = "0" * 64
        write_json(path, manifest)
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("boot_evidence.bios_sha256" in item for item in found), found)

    def test_unsafe_asset_paths_are_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        line = f"{'0' * 64}  ../outside"
        sums.write_text(sums.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("unsafe asset name" in item for item in found), found)

    def test_symlink_assets_are_refused(self) -> None:
        image = self.directory / "image.iso"
        image.unlink()
        image.symlink_to(self.directory / "build-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("image.iso must not be a symlink" in item for item in found), found)

    def test_malformed_sums_are_refused(self) -> None:
        (self.directory / "SHA256SUMS").write_text("not a checksum line\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("malformed SHA256SUMS line 1" in item for item in found), found)

    def test_duplicate_sums_entries_are_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        line = next(
            line for line in sums.read_text(encoding="utf-8").splitlines()
            if line.endswith("  image.iso")
        )
        sums.write_text(sums.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("duplicate SHA256SUMS entry: image.iso" in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
