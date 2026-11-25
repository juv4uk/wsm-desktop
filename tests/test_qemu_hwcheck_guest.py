# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-side tests for the isolated wsm-hwcheck QEMU guest builder."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib.util

_GUEST_SCRIPT = ROOT / "scripts" / "ci_qemu_hwcheck_guest.py"
_GUEST_SPEC = importlib.util.spec_from_file_location("wsm_qemu_guest_script", _GUEST_SCRIPT)
if _GUEST_SPEC is None or _GUEST_SPEC.loader is None:
    raise RuntimeError(f"cannot load guest runner from {_GUEST_SCRIPT}")
_GUEST_MODULE = importlib.util.module_from_spec(_GUEST_SPEC)
sys.modules[_GUEST_SPEC.name] = _GUEST_MODULE
_GUEST_SPEC.loader.exec_module(_GUEST_MODULE)

GuestRunError = _GUEST_MODULE.GuestRunError
MAX_INITRAMFS_BYTES = _GUEST_MODULE.MAX_INITRAMFS_BYTES
MAX_PYTHON_ARCHIVE_BYTES = _GUEST_MODULE.MAX_PYTHON_ARCHIVE_BYTES
extract_python_archive = _GUEST_MODULE.extract_python_archive
extract_report = _GUEST_MODULE.extract_report
write_guest_init = _GUEST_MODULE.write_guest_init


class GuestReportExtractionTests(unittest.TestCase):
    REPORT = {"schema_version": "1.0.0", "devices": [], "privacy": {"network_requests_performed": False}}

    def test_extracts_lf_serial_report(self) -> None:
        payload = json.dumps(self.REPORT, separators=(",", ":")).encode("utf-8")
        serial = (
            b"kernel boot\nWSM_HWCHECK_REPORT_BEGIN\n"
            + payload
            + b"\nWSM_HWCHECK_REPORT_END\nreboot\n"
        )
        self.assertEqual(extract_report(serial), self.REPORT)

    def test_extracts_crlf_serial_report(self) -> None:
        payload = json.dumps(self.REPORT, separators=(",", ":")).encode("utf-8")
        serial = (
            b"kernel boot\r\nWSM_HWCHECK_REPORT_BEGIN\r\n"
            + payload
            + b"\r\nWSM_HWCHECK_REPORT_END\r\nreboot\r\n"
        )
        self.assertEqual(extract_report(serial), self.REPORT)

    def test_uses_last_complete_report_when_guest_prints_diagnostic_markers(self) -> None:
        payload = json.dumps(self.REPORT, separators=(",", ":")).encode("utf-8")
        serial = (
            b"WSM_HWCHECK_REPORT_BEGIN\ntruncated earlier report\n"
            b"WSM_HWCHECK_REPORT_BEGIN\n"
            + payload
            + b"\nWSM_HWCHECK_REPORT_END\n"
        )
        self.assertEqual(extract_report(serial), self.REPORT)

    def test_rejects_missing_or_incomplete_report_markers(self) -> None:
        with self.assertRaisesRegex(GuestRunError, "begin marker"):
            extract_report(b"kernel booted\nno report\n")
        with self.assertRaisesRegex(GuestRunError, "end marker"):
            extract_report(b"WSM_HWCHECK_REPORT_BEGIN\n{}")

    def test_rejects_non_json_report_payload(self) -> None:
        with self.assertRaisesRegex(GuestRunError, "not valid UTF-8 JSON"):
            extract_report(
                b"WSM_HWCHECK_REPORT_BEGIN\nnot-json\nWSM_HWCHECK_REPORT_END\n"
            )


class GuestInitTemplateTests(unittest.TestCase):
    def test_guest_init_renders_valid_shell_and_all_stage_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_guest_init(
                root,
                {"/lib/x86_64-linux-gnu", "/opt/python/lib"},
            )
            init = root / "init"
            rendered = init.read_text(encoding="utf-8")

            self.assertTrue(init.stat().st_mode & 0o111)
            self.assertIn("WSM_HWCHECK_GUEST_INIT_STARTED", rendered)
            self.assertIn("WSM_HWCHECK_GUEST_MOUNTS_READY", rendered)
            self.assertIn("WSM_HWCHECK_GUEST_PYTHON_START", rendered)
            self.assertIn("WSM_HWCHECK_GUEST_COLLECTOR_START", rendered)
            self.assertIn("WSM_HWCHECK_GUEST_REPORT_READY", rendered)
            self.assertIn("WSM_HWCHECK_REPORT_BEGIN", rendered)
            self.assertIn("WSM_HWCHECK_REPORT_END", rendered)
            self.assertNotIn("{{", rendered)
            self.assertNotIn("}}", rendered)

            checked = subprocess.run(
                ["sh", "-n", str(init)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(
                checked.returncode,
                0,
                checked.stderr,
            )


class GuestArchiveSafetyTests(unittest.TestCase):
    def test_resource_caps_are_explicit(self) -> None:
        self.assertEqual(MAX_PYTHON_ARCHIVE_BYTES, 40 * 1024 * 1024)
        self.assertEqual(MAX_INITRAMFS_BYTES, 256 * 1024 * 1024)

    def test_rejects_tar_path_traversal_without_writing_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            archive_path = parent / "malicious.tar.gz"
            destination = parent / "extract"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"must not escape"
                member = tarfile.TarInfo("../escaped.txt")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))

            with self.assertRaises(GuestRunError):
                extract_python_archive(archive_path, destination)
            self.assertFalse((parent / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main()
