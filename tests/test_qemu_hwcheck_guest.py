# SPDX-License-Identifier: LicenseRef-Volnist
"""Host-side safety tests for the QEMU-hosted WSM hardware checker."""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ci_qemu_hwcheck_guest as guest


class FakeResponse:
    def __init__(self, chunks: list[bytes], content_length: str | None = None) -> None:
        self.chunks = list(chunks)
        self.status = 200
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.read_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        self.read_calls += 1
        return self.chunks.pop(0) if self.chunks else b""


def write_tar(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


class QemuHwcheckGuestSafetyTests(unittest.TestCase):
    def test_guest_init_template_renders_all_stages_without_placeholders(self) -> None:
        rendered = guest.render_guest_init("/lib:/lib64:/opt/python/lib")

        for marker in (
            "WSM_HWCHECK_STAGE_INIT",
            "WSM_HWCHECK_STAGE_PYTHON_IMPORT",
            "WSM_HWCHECK_STAGE_COLLECTOR_START",
            "WSM_HWCHECK_STAGE_COLLECTOR_DONE",
            "WSM_HWCHECK_REPORT_BEGIN",
            "WSM_HWCHECK_REPORT_END",
            "WSM_HWCHECK_GUEST_FAILURE:",
            "WSM_INSTALL_STAGE_START",
            "WSM_INSTALL_STAGE_DONE",
            "WSM_INSTALL_PLAN_RESULT:",
        ):
            self.assertIn(marker, rendered)

        self.assertIn("guest_fail() {", rendered)
        self.assertIn("export LD_LIBRARY_PATH=/lib:/lib64:/opt/python/lib", rendered)
        self.assertIn("guest report exceeds the 512 KiB report ceiling", rendered)
        self.assertIn("--preflight", rendered)
        self.assertIn("--dry-run", rendered)
        self.assertEqual(rendered.count("export WSM_HWCHECK_REPORT=/tmp/hardware-report.json"), 1)
        self.assertEqual(rendered.count('--output "$WSM_HWCHECK_REPORT"'), 1)
        self.assertEqual(rendered.count('"--report", os.environ["WSM_HWCHECK_REPORT"]'), 1)
        self.assertEqual(rendered.count('Path(os.environ["WSM_HWCHECK_REPORT"])'), 2)
        self.assertNotIn("desktop-observed.json", rendered)
        self.assertNotIn("/opt/wsm/fixtures", rendered)
        self.assertIn("socket.create_connection = deny_host_io", rendered)
        self.assertIn("subprocess.Popen = deny_host_io", rendered)
        self.assertNotIn("{max_installer_plan_bytes}", rendered)
        self.assertNotIn("{ld_library_path}", rendered)
        self.assertNotIn("{max_report_bytes}", rendered)

    def test_guest_validator_dependency_allowlist_is_explicit(self) -> None:
        self.assertEqual(guest.GUEST_JSONSCHEMA_VERSION, "4.26.0")
        for name in (
            "jsonschema", "jsonschema-specifications", "referencing", "rpds-py",
            "attrs", "fqdn", "idna", "isoduration", "rfc3339-validator", "rfc3987",
            "uri-template", "webcolors", "jsonpointer", "arrow", "python-dateutil",
            "six", "typing-extensions", "tzdata",
        ):
            self.assertIn(name, guest.GUEST_VALIDATION_DISTRIBUTIONS)
        self.assertNotIn("pip", guest.GUEST_VALIDATION_DISTRIBUTIONS)

    def test_guest_distribution_copy_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "site-packages"
            destination = root / "guest-root" / "site-packages"
            (source / "jsonschema").mkdir(parents=True)
            (source / "jsonschema" / "__init__.py").write_text("SAFE = True", encoding="utf-8")
            (source.parent / "outside.py").write_text("UNSAFE = True", encoding="utf-8")
            distribution = SimpleNamespace(
                files=(Path("jsonschema/__init__.py"), Path("../outside.py")),
                locate_file=lambda entry: source / Path(str(entry)),
            )
            copied = guest._copy_guest_distribution_files(distribution, source, destination)
            self.assertEqual(copied, 1)
            self.assertEqual(
                (destination / "jsonschema" / "__init__.py").read_text(encoding="utf-8"),
                "SAFE = True",
            )
            self.assertFalse((destination.parent / "outside.py").exists())
            self.assertEqual((source.parent / "outside.py").read_text(encoding="utf-8"), "UNSAFE = True")

    def test_guest_installer_plan_marker_accepts_only_non_confirmable_dry_run(self) -> None:
        marker = (
            "WSM_INSTALL_PLAN_RESULT:status=diagnostic-only;confirmable=false;"
            "backend=guix-system;dry_run=true;mutations_authorized=false;"
            "backend_invoked=false;disk_access_performed=false;plan_sha256=" + "a" * 64
        )
        serial = "WSM_INSTALL_STAGE_START\n" + marker + "\nWSM_INSTALL_STAGE_DONE\n"
        result = guest._validate_installer_plan_result(serial)
        self.assertEqual(result["status"], "diagnostic-only")
        self.assertEqual(result["backend"], "guix-system")
        self.assertEqual(result["backend_invoked"], "false")
        with self.assertRaisesRegex(RuntimeError, "violated backend_invoked"):
            guest._validate_installer_plan_result(
                serial.replace("backend_invoked=false", "backend_invoked=true")
            )
        with self.assertRaisesRegex(RuntimeError, "missing or unexpected fields"):
            guest._validate_installer_plan_result(
                serial.replace(";plan_sha256=" + "a" * 64, "")
            )
        with self.assertRaisesRegex(RuntimeError, "missing or unexpected fields"):
            guest._validate_installer_plan_result(
                serial.replace(";plan_sha256=" + "a" * 64, ";extra=unexpected;plan_sha256=" + "a" * 64)
            )
        with self.assertRaisesRegex(RuntimeError, "valid canonical plan digest"):
            guest._validate_installer_plan_result(
                serial.replace("plan_sha256=" + "a" * 64, "plan_sha256=not-a-digest")
            )

    def test_guest_installer_plan_marker_rejects_missing_or_duplicate_markers(self) -> None:
        marker = (
            "WSM_INSTALL_PLAN_RESULT:status=diagnostic-only;confirmable=false;"
            "backend=guix-system;dry_run=true;mutations_authorized=false;"
            "backend_invoked=false;disk_access_performed=false;plan_sha256=" + "b" * 64
        )
        with self.assertRaisesRegex(RuntimeError, "stage markers"):
            guest._validate_installer_plan_result("WSM_INSTALL_STAGE_START\n" + marker)
        valid = "WSM_INSTALL_STAGE_START\n" + marker + "\nWSM_INSTALL_STAGE_DONE\n"
        with self.assertRaisesRegex(RuntimeError, "expected one"):
            guest._validate_installer_plan_result(valid + marker + "\n")

    def test_busybox_links_cover_every_init_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            (bin_dir / "busybox").write_bytes(b"synthetic busybox")

            guest._install_busybox_applets(bin_dir)

            self.assertEqual(
                set(guest.BUSYBOX_APPLETS),
                {"sh", "mount", "mkdir", "poweroff", "sleep", "sync"},
            )
            for applet in guest.BUSYBOX_APPLETS:
                link = bin_dir / applet
                self.assertTrue(link.is_symlink(), applet)
                self.assertEqual(link.readlink(), Path("busybox"))

    def test_download_rejects_oversized_content_length_before_reading(self) -> None:
        response = FakeResponse([b"payload"], content_length="5")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "python.tar.gz"
            with patch.object(guest, "MAX_PYTHON_ARCHIVE_BYTES", 4), patch.object(
                guest.urllib.request, "urlopen", return_value=response
            ):
                with self.assertRaisesRegex(RuntimeError, "40 MiB"):
                    guest._download_pinned_python(destination)
            self.assertEqual(response.read_calls, 0)

    def test_download_stream_stops_before_writing_over_limit(self) -> None:
        response = FakeResponse([b"1234", b"5678"])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "python.tar.gz"
            with patch.object(guest, "MAX_PYTHON_ARCHIVE_BYTES", 4), patch.object(
                guest.urllib.request, "urlopen", return_value=response
            ):
                with self.assertRaisesRegex(RuntimeError, "40 MiB"):
                    guest._download_pinned_python(destination)
            self.assertEqual(destination.stat().st_size, 4)

    def test_download_verifies_exact_archive_digest(self) -> None:
        payload = b"pinned test archive"
        response = FakeResponse([payload[:7], payload[7:]])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "python.tar.gz"
            with patch.object(
                guest, "PYTHON_SHA256", hashlib.sha256(payload).hexdigest()
            ), patch.object(guest, "MAX_PYTHON_ARCHIVE_BYTES", 1024), patch.object(
                guest.urllib.request, "urlopen", return_value=response
            ):
                guest._download_pinned_python(destination)
            self.assertEqual(destination.read_bytes(), payload)

    def test_tar_extraction_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.tar.gz"
            write_tar(archive, [("../outside.txt", b"unsafe")])
            destination = root / "extract"
            destination.mkdir()
            with self.assertRaisesRegex(RuntimeError, "unsafe path"):
                guest._safe_extract_tar(archive, destination)
            self.assertFalse((root / "outside.txt").exists())

    def test_tar_extraction_enforces_member_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "many.tar.gz"
            write_tar(archive, [("one", b"1"), ("two", b"2")])
            destination = root / "extract"
            destination.mkdir()
            with patch.object(guest, "MAX_TAR_MEMBERS", 1):
                with self.assertRaisesRegex(RuntimeError, "too many entries"):
                    guest._safe_extract_tar(archive, destination)

    def test_tar_extraction_enforces_expanded_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "large.tar.gz"
            write_tar(archive, [("large.bin", b"12345")])
            destination = root / "extract"
            destination.mkdir()
            with patch.object(guest, "MAX_TAR_EXPANDED_BYTES", 4):
                with self.assertRaisesRegex(RuntimeError, "256 MiB"):
                    guest._safe_extract_tar(archive, destination)

    def test_tar_extraction_accepts_a_small_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "safe.tar.gz"
            write_tar(archive, [("python/README", b"safe")])
            destination = root / "extract"
            destination.mkdir()
            guest._safe_extract_tar(archive, destination)
            self.assertEqual((destination / "python" / "README").read_bytes(), b"safe")

    def test_report_transport_round_trips_crlf_serial_output(self) -> None:
        import base64
        import gzip
        import json

        expected = {"schema_version": "1.0.0", "devices": []}
        encoded = base64.b64encode(
            gzip.compress(json.dumps(expected).encode("utf-8"), mtime=0)
        ).decode("ascii")
        serial = (chr(13) + chr(10)).join(
            (
                guest.REPORT_BEGIN,
                guest.REPORT_PREFIX + encoded,
                guest.REPORT_END,
            )
        )
        self.assertEqual(guest._decode_guest_report(serial), expected)

    def test_report_decoder_rejects_gzip_expansion_over_the_limit(self) -> None:
        import base64
        import gzip

        oversized = b"x" * (guest.MAX_REPORT_BYTES + 1)
        encoded = base64.b64encode(gzip.compress(oversized, mtime=0)).decode("ascii")
        serial = chr(10).join(
            (
                guest.REPORT_BEGIN,
                guest.REPORT_PREFIX + encoded,
                guest.REPORT_END,
            )
        )
        with self.assertRaisesRegex(RuntimeError, "512 KiB"):
            guest._decode_guest_report(serial)

    def test_guest_size_limits_are_explicit(self) -> None:
        self.assertEqual(guest.MAX_PYTHON_ARCHIVE_BYTES, 40 * 1024 * 1024)
        self.assertEqual(guest.MAX_TAR_MEMBERS, 50_000)
        self.assertEqual(guest.MAX_TAR_EXPANDED_BYTES, 256 * 1024 * 1024)
        self.assertEqual(guest.MAX_INITRAMFS_BYTES, 256 * 1024 * 1024)
        self.assertEqual(guest.MAX_REPORT_BYTES, 512 * 1024)


if __name__ == "__main__":
    unittest.main()
