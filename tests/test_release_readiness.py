# SPDX-License-Identifier: LicenseRef-Volnist
"""A draft's claims must be backed by the evidence shipped beside them."""

from __future__ import annotations

import importlib.util
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
    digest = checker.sha256_of(directory / "image.iso")
    manifest["artifact"]["sha256"] = digest
    (directory / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    sums = [
        f"{digest}  image.iso",
        f"{checker.sha256_of(directory / 'boot-bios.json')}  boot-bios.json",
        f"{checker.sha256_of(directory / 'boot-uefi.json')}  boot-uefi.json",
        f"{checker.sha256_of(directory / 'release-manifest.json')}  release-manifest.json",
    ]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        build(self.directory)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_consistent_draft_is_ready(self) -> None:
        self.assertEqual(checker.problems(self.directory, require_iso=True), [])

    def test_installer_claim_without_execution_is_refused(self) -> None:
        build(self.directory, installer_executed=False)
        found = checker.problems(self.directory)
        self.assertTrue(any("guest_installer_execution false" in item for item in found), found)

    def test_installer_claim_without_marker_is_refused(self) -> None:
        build(self.directory, marker="WSM_LIVE_READY")
        record = json.loads((self.directory / "boot-bios.json").read_text(encoding="utf-8"))
        record["serial_output_tail"] = "WSM_LIVE_READY only"
        (self.directory / "boot-bios.json").write_text(json.dumps(record), encoding="utf-8")
        found = checker.problems(self.directory)
        self.assertTrue(any("never showed WSM_INSTALLER_OK" in item for item in found), found)

    def test_a_missing_asset_is_refused(self) -> None:
        (self.directory / "boot-uefi.json").unlink()
        found = checker.problems(self.directory)
        self.assertIn("missing boot-uefi.json", found)

    def test_a_corrupted_image_is_refused(self) -> None:
        (self.directory / "image.iso").write_bytes(b"tampered")
        found = checker.problems(self.directory, require_iso=True)
        self.assertTrue(any("does not match its recorded hash" in item for item in found), found)

    def test_an_absent_image_is_reported_only_when_required(self) -> None:
        (self.directory / "image.iso").unlink()
        self.assertEqual(checker.problems(self.directory), [])
        self.assertTrue(checker.problems(self.directory, require_iso=True))


if __name__ == "__main__":
    unittest.main()
