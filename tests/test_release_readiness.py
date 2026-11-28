# SPDX-License-Identifier: LicenseRef-Volnist
"""A draft's claims must be backed by the complete evidence shipped beside them."""

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


def build(directory: Path, installer_executed: bool = True, marker: str = "WSM_LIVE_READY") -> None:
    boot = {
        "boot_confirmed": True,
        "guest_installer_execution": installer_executed,
        "serial_output_tail": f"...{marker}...WSM_INSTALLER_OK...",
    }
    for name in ("boot-bios.json", "boot-uefi.json"):
        (directory / name).write_text(json.dumps(boot), encoding="utf-8")
    manifest = {
        "acceptance": {
            "bios": "pass",
            "uefi": "pass",
            "installer": "pass",
            "marker": marker,
            "installer_marker": "WSM_INSTALLER_OK",
        },
        "artifact": {"filename": "image.iso", "sha256": "0" * 64},
        "boot_evidence": {},
    }
    (directory / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "image.iso").write_bytes(b"iso")
    manifest["artifact"]["sha256"] = checker.sha256_of(directory / "image.iso")
    (directory / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_sums(directory)


def write_sums(directory: Path, extra: tuple[str, ...] = ()) -> None:
    names = ("image.iso", "boot-bios.json", "boot-uefi.json", "release-manifest.json", *extra)
    lines = []
    for name in names:
        path = directory / name
        if path.is_file():
            lines.append(f"{checker.sha256_of(path)}  {name}")
        else:
            lines.append(f"{'0' * 64}  {name}")
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


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        build(self.directory)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_consistent_draft_is_ready_by_default(self) -> None:
        self.assertEqual(checker.problems(self.directory), [])

    def test_installer_claim_without_execution_is_refused(self) -> None:
        build(self.directory, installer_executed=False)
        found = checker.problems(self.directory)
        self.assertTrue(any("guest_installer_execution false" in item for item in found), found)

    def test_installer_claim_without_serial_marker_is_refused(self) -> None:
        build(self.directory)
        record = json.loads((self.directory / "boot-bios.json").read_text(encoding="utf-8"))
        record["serial_output_tail"] = "WSM_LIVE_READY only"
        (self.directory / "boot-bios.json").write_text(json.dumps(record), encoding="utf-8")
        rewrite_checksum(self.directory, "boot-bios.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("never showed WSM_INSTALLER_OK" in item for item in found), found)

    def test_missing_manifest_marker_is_refused(self) -> None:
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["acceptance"]["marker"] = ""
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("manifest marker is missing" in item for item in found), found)

    def test_missing_installer_marker_is_refused(self) -> None:
        manifest_path = self.directory / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["acceptance"]["installer_marker"] = None
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rewrite_checksum(self.directory, "release-manifest.json")
        found = checker.problems(self.directory)
        self.assertTrue(any("manifest installer_marker is missing" in item for item in found), found)

    def test_a_missing_required_evidence_asset_is_refused(self) -> None:
        (self.directory / "boot-uefi.json").unlink()
        found = checker.problems(self.directory)
        self.assertTrue(any("missing boot-uefi.json" in item for item in found), found)

    def test_a_missing_sha256sums_listed_asset_is_refused(self) -> None:
        write_sums(self.directory, extra=("build-manifest.json",))
        found = checker.problems(self.directory)
        self.assertTrue(any("build-manifest.json is listed in SHA256SUMS but is absent" in item for item in found), found)

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

    def test_malformed_sums_are_refused(self) -> None:
        (self.directory / "SHA256SUMS").write_text("not a checksum line\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("malformed SHA256SUMS line 1" in item for item in found), found)

    def test_duplicate_sums_entries_are_refused(self) -> None:
        sums = self.directory / "SHA256SUMS"
        line = next(line for line in sums.read_text(encoding="utf-8").splitlines() if line.endswith("  image.iso"))
        sums.write_text(sums.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("duplicate SHA256SUMS entry: image.iso" in item for item in found), found)


if __name__ == "__main__":
    unittest.main()
