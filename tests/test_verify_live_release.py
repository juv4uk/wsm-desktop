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
    check_boot_records,
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


def make_bootable_iso(path: Path, platforms: tuple[int, ...] = (0, 0xEF)) -> None:
    """Write a minimal ISO9660 + El Torito image with the given firmware entries."""
    import struct

    size = 24 * 2048
    data = bytearray(size)
    data[0x8001:0x8006] = b"CD001"
    # Primary volume descriptor.
    data[16 * 2048] = 1
    data[16 * 2048 + 1:16 * 2048 + 6] = b"CD001"
    # Boot record descriptor pointing at a catalogue on sector 20.
    boot = 17 * 2048
    data[boot] = 0
    data[boot + 1:boot + 6] = b"CD001"
    data[boot + 7:boot + 30] = b"EL TORITO SPECIFICATION"
    data[boot + 71:boot + 75] = struct.pack("<I", 20)
    # Catalogue.
    catalogue = 20 * 2048
    data[catalogue] = 1
    data[catalogue + 1] = platforms[0]
    entry = catalogue + 32
    data[entry] = 0x88
    data[entry + 6:entry + 8] = struct.pack("<H", 4)
    data[entry + 8:entry + 12] = struct.pack("<I", 100)
    position = catalogue + 64
    for index, platform in enumerate(platforms[1:]):
        final = 0x90 if index == len(platforms) - 2 else 0x91
        data[position] = final
        data[position + 1] = platform
        data[position + 2:position + 4] = struct.pack("<H", 1)
        sub = position + 32
        data[sub] = 0x88
        data[sub + 6:sub + 8] = struct.pack("<H", 5760)
        data[sub + 8:sub + 12] = struct.pack("<I", 200)
        position += 64
    path.write_bytes(bytes(data))


class BootRecordTests(unittest.TestCase):
    def test_bios_and_uefi_is_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "x.iso"
            make_bootable_iso(iso, (0, 0xEF))
            result = check_boot_records(iso)
        self.assertEqual(result["status"], "pass", result["detail"])
        self.assertIn("UEFI", result["detail"])

    def test_only_bios_is_a_failure(self) -> None:
        """Acceptance requires both firmwares; one is not enough."""
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "x.iso"
            make_bootable_iso(iso, (0,))
            result = check_boot_records(iso)
        self.assertEqual(result["status"], "fail")
        self.assertIn("only one firmware", result["detail"])

    def test_image_without_boot_record_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "x.iso"
            iso.write_bytes(b"\0" * (24 * 2048))
            result = check_boot_records(iso)
        self.assertEqual(result["status"], "fail")
        self.assertIn("not bootable media", result["detail"])

    def test_missing_file_is_a_failure_not_a_crash(self) -> None:
        result = check_boot_records(Path("/nonexistent.iso"))
        self.assertEqual(result["status"], "fail")


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
            # A bootable image, so that only the missing --boot flag makes the
            # verdict incomplete. A non-bootable fixture would fail the
            # boot-records criterion and hide what this test is about.
            iso = directory / "wsm-desktop-test.iso"
            make_bootable_iso(iso, (0, 0xEF))
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



class RecordedVerdictTests(unittest.TestCase):
    """The verdict committed to the repository must match the tool's schema."""

    def test_recorded_iso_verdict_is_wellformed(self) -> None:
        path = ROOT / "docs" / "artifacts" / "iso-verdict-0.1.0-rc2-live-iso.json"
        verdict = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(verdict["schema"], "wsm-release-verdict/1")
        self.assertIn(verdict["overall"], {"pass", "fail", "incomplete"})
        ids = {item["id"] for item in verdict["criteria"]}
        for expected in ("checksum", "iso-structure", "boot-records"):
            self.assertIn(expected, ids)
        self.assertEqual(verdict["artifact"], "wsm-desktop-kde-hardened-20261125.iso")

    def test_recorded_verdict_does_not_claim_a_pass(self) -> None:
        """It was never booted; claiming otherwise would be the exact failure mode."""
        path = ROOT / "docs" / "artifacts" / "iso-verdict-0.1.0-rc2-live-iso.json"
        verdict = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotEqual(verdict["overall"], "pass")
        statuses = {item["id"]: item["status"] for item in verdict["criteria"]}
        self.assertEqual(statuses["boot-bios"], "not-run")
        self.assertEqual(statuses["boot-uefi"], "not-run")

class PartsTests(unittest.TestCase):
    """A release published as parts must still be verifiable as published."""

    def make_parts(self, directory, payload=b"x" * 8192, count=2):
        image = directory / "WSM-Desktop-fixture.iso"
        image.write_bytes(payload)
        subprocess.run(["split", "-b", str(len(payload) // count + 1), "-d", "-a", "3",
                        str(image), str(image) + ".part"], check=True)
        image.unlink()
        return sorted(directory.glob("*.iso.part*"))

    def test_join_parts_rebuilds_the_same_bytes(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_live_release import join_parts

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            payload = bytes(range(256)) * 64
            parts = self.make_parts(directory, payload)
            joined = join_parts(parts, directory / "joined.iso")
            self.assertEqual(joined.read_bytes(), payload)

    def test_join_parts_uses_lexical_order(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_live_release import join_parts

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            payload = b"0" * 3000 + b"1" * 3000 + b"2" * 3000
            parts = self.make_parts(directory, payload, count=3)
            joined = join_parts(parts, directory / "joined.iso")
            self.assertEqual(joined.read_bytes(), payload)

    def test_discover_parts_rejects_a_duplicate_suffix(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_live_release import discover_parts

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "a.iso.part000").write_bytes(b"x")
            (directory / "b.iso.part000").write_bytes(b"y")
            with self.assertRaises(ValueError):
                discover_parts(directory)

    def test_verifier_reassembles_when_given_a_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            parts = self.make_parts(directory)
            result = subprocess.run(
                [sys.executable, "scripts/verify_live_release.py",
                 "--iso", str(parts[0]), "--compact"],
                capture_output=True, text=True, cwd=ROOT,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["artifact"], "WSM-Desktop-fixture.iso")
            self.assertTrue(payload["artifact_source"].startswith("parts"))



if __name__ == "__main__":
    unittest.main()
