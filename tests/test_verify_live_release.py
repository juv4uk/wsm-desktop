# SPDX-License-Identifier: LicenseRef-Volnist
"""The verdict must fail loudly and refuse to call a skipped check a pass."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_live_release import (  # noqa: E402
    ISO_MAGIC_OFFSET,
    check_checksum,
    check_iso_structure,
    check_manifest,
    parse_sums,
    verdict,
)


def make_iso(directory: Path, name: str = "wsm-desktop.iso", magic: bytes = b"CD001") -> Path:
    path = directory / name
    payload = bytearray(ISO_MAGIC_OFFSET + 16)
    payload[ISO_MAGIC_OFFSET:ISO_MAGIC_OFFSET + len(magic)] = magic
    path.write_bytes(bytes(payload))
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict_for(criteria: list[dict[str, str]]) -> dict:
    """Create a real temporary artifact because verdicts bind the exact ISO bytes."""
    with tempfile.TemporaryDirectory() as temporary:
        iso = Path(temporary) / "x.iso"
        iso.write_bytes(b"release-verdict fixture")
        return verdict(criteria, iso)


class ChecksumTests(unittest.TestCase):
    def test_matching_checksum_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            result = check_checksum(iso, {iso.name: digest(iso)})
        self.assertEqual(result["status"], "pass")

    def test_mismatch_fails_and_names_both_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            result = check_checksum(iso, {iso.name: "0" * 64})
        self.assertEqual(result["status"], "fail")
        self.assertIn("0" * 64, result["detail"])

    def test_missing_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            result = check_checksum(iso, {})
        self.assertEqual(result["status"], "fail")

    def test_sums_file_is_parsed_with_star_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SHA256SUMS"
            path.write_text("a" * 64 + " *file.iso\n\n# comment\n", encoding="utf-8")
            self.assertEqual(parse_sums(path), {"file.iso": "a" * 64})


class StructureTests(unittest.TestCase):
    def test_real_iso_magic_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = check_iso_structure(make_iso(Path(temporary)))
        self.assertEqual(result["status"], "pass")

    def test_wrong_magic_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = check_iso_structure(make_iso(Path(temporary), magic=b"XXXXX"))
        self.assertEqual(result["status"], "fail")
        self.assertIn("not a bootable ISO", result["detail"])

    def test_tiny_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "wsm-desktop.iso"
            path.write_bytes(b"tiny")
            result = check_iso_structure(path)
        self.assertEqual(result["status"], "fail")


class ManifestTests(unittest.TestCase):
    def test_manifest_must_describe_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            result = check_manifest(iso, {"files": []}, {iso.name: digest(iso)})
        self.assertEqual(result["status"], "fail")

    def test_disagreement_between_manifest_and_sums_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            manifest = {"files": [{"name": iso.name, "sha256": "1" * 64}]}
            result = check_manifest(iso, manifest, {iso.name: digest(iso)})
        self.assertEqual(result["status"], "fail")

    def test_agreement_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = make_iso(Path(temporary))
            manifest = {"files": [{"name": iso.name, "sha256": digest(iso)}]}
            result = check_manifest(iso, manifest, {iso.name: digest(iso)})
        self.assertEqual(result["status"], "pass")


class VerdictTests(unittest.TestCase):
    def test_skipped_check_makes_the_verdict_incomplete_not_passing(self) -> None:
        criteria = [
            {"id": "checksum", "status": "pass", "detail": ""},
            {"id": "boot-bios", "status": "not-run", "detail": "no qemu"},
        ]
        self.assertEqual(verdict_for(criteria)["overall"], "incomplete")

    def test_any_failure_fails_the_whole_verdict(self) -> None:
        criteria = [
            {"id": "checksum", "status": "pass", "detail": ""},
            {"id": "boot-uefi", "status": "fail", "detail": "no marker"},
        ]
        self.assertEqual(verdict_for(criteria)["overall"], "fail")

    def test_all_pass_is_a_pass(self) -> None:
        criteria = [{"id": "checksum", "status": "pass", "detail": ""}]
        self.assertEqual(verdict_for(criteria)["overall"], "pass")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_live_release.py"), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_bad_checksum_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            iso = make_iso(directory)
            (directory / "SHA256SUMS").write_text(f"{'0' * 64}  {iso.name}\n", encoding="utf-8")
            result = self.run_cli("--iso", str(iso), "--compact")
        self.assertEqual(result.returncode, 1)
        self.assertIn('"overall": "fail"', result.stdout)

    def test_missing_boot_flag_is_recorded_as_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            iso = make_iso(directory)
            (directory / "SHA256SUMS").write_text(
                f"{digest(iso)}  {iso.name}\n", encoding="utf-8"
            )
            result = self.run_cli("--iso", str(iso), "--compact")
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["overall"], "incomplete")
        statuses = {item["id"]: item["status"] for item in payload["criteria"]}
        self.assertEqual(statuses["boot-bios"], "not-run")
        self.assertEqual(statuses["checksum"], "pass")


if __name__ == "__main__":
    unittest.main()
