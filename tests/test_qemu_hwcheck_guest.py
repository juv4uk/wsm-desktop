# SPDX-License-Identifier: GPL-3.0-or-later
"""Safety tests for the QEMU-hosted WSM hardware-checker guest runner."""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def test_busybox_links_cover_every_init_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            (bin_dir / "busybox").write_bytes(b"synthetic busybox")

            guest._install_busybox_applets(bin_dir)

            self.assertEqual(set(guest.BUSYBOX_APPLETS), {
                "sh", "mount", "mkdir", "sleep", "sync", "poweroff"
            })
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

    def test_guest_initramfs_limits_are_explicit(self) -> None:
        self.assertEqual(guest.MAX_PYTHON_ARCHIVE_BYTES, 40 * 1024 * 1024)
        self.assertEqual(guest.MAX_TAR_MEMBERS, 50_000)
        self.assertEqual(guest.MAX_TAR_EXPANDED_BYTES, 256 * 1024 * 1024)
        self.assertEqual(guest.MAX_INITRAMFS_BYTES, 256 * 1024 * 1024)
        self.assertEqual(guest.MAX_REPORT_BYTES, 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
