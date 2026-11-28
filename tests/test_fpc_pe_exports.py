# SPDX-License-Identifier: LicenseRef-Volnist
"""Behavioral parity tests for the Free Pascal PE export reader.

All PE fixtures are generated in memory. No vendor binary is shipped in the
repository, and no image is loaded or executed by the reader under test.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "fpc-pe" / "wsm_pe_exports.lpr"


def find_fpc() -> str | None:
    found = shutil.which("fpc")
    if found:
        return found
    known = Path(r"C:\fpcupdeluxe\fpc\bin\x86_64-win64\fpc.exe")
    return str(known) if known.is_file() else None


def build_pe(
    entries: list[tuple[str | None, int, str | None]],
    *,
    export_rva: int | None = 0x1000,
    base: int = 1,
) -> bytes:
    """Build a minimal PE32+ image with one mapped .rdata section."""
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 0xF0, 0x2022)
    opt = bytearray(0xF0)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<Q", opt, 24, 0x180000000)
    struct.pack_into("<I", opt, 32, 0x1000)
    struct.pack_into("<I", opt, 36, 0x200)
    struct.pack_into("<I", opt, 108, 16)
    if export_rva is not None:
        struct.pack_into("<II", opt, 112, export_rva, 0x200)
    section = struct.pack(
        "<8sIIIIIIHHI",
        b".rdata\0\0", 0x200, 0x1000, 0x200, 0x400, 0, 0, 0, 0, 0x40000040,
    )

    data = bytearray(0x200)
    named = [(i, entry) for i, entry in enumerate(entries) if entry[0]]
    struct.pack_into(
        "<IIHHIIIIIII", data, 0,
        0, 0, 0, 0, 0x1180, base, len(entries), len(named), 0x1040, 0x1080, 0x10A0,
    )
    cursor = 0xC0
    for i, (_name, rva, forwarder) in enumerate(entries):
        if forwarder is not None:
            encoded = forwarder.encode("ascii") + b"\0"
            data[cursor:cursor + len(encoded)] = encoded
            struct.pack_into("<I", data, 0x40 + 4 * i, export_rva + cursor)
            cursor += len(encoded)
        else:
            struct.pack_into("<I", data, 0x40 + 4 * i, rva)
    for slot, (i, (name, _rva, _forwarder)) in enumerate(named):
        encoded = name.encode("ascii") + b"\0"
        data[cursor:cursor + len(encoded)] = encoded
        struct.pack_into("<I", data, 0x80 + 4 * slot, export_rva + cursor)
        struct.pack_into("<H", data, 0xA0 + 2 * slot, i)
        cursor += len(encoded)
    data[0x180:0x180 + 12] = b"fixture.dll\0"

    prefix = bytes(dos + b"PE\0\0" + coff + opt + section)
    return prefix + b"\0" * (0x400 - len(prefix)) + bytes(data)


@unittest.skipUnless(find_fpc(), "Free Pascal compiler is not available")
class FpcPeExportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        proc = subprocess.run(
            [find_fpc(), "-Mobjfpc", f"-FE{cls.dir}", f"-FU{cls.dir}", str(SOURCE)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            cls.tmp.cleanup()
            raise AssertionError(f"fpc failed: {proc.stdout}\n{proc.stderr}")
        exe = cls.dir / ("wsm_pe_exports.exe" if os.name == "nt" else "wsm_pe_exports")
        if not exe.is_file():
            cls.tmp.cleanup()
            raise AssertionError(f"compiler produced no binary: {sorted(p.name for p in cls.dir.iterdir())}")
        cls.exe = exe

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_tool(self, data: bytes) -> subprocess.CompletedProcess[str]:
        target = self.dir / "fixture.dll"
        target.write_bytes(data)
        return subprocess.run(
            [str(self.exe), str(target)], capture_output=True, text=True,
        )

    def test_named_exports(self) -> None:
        proc = self.run_tool(build_pe([
            ("FxDriverEntryUm", 0x2000, None),
            ("__ImagePolicyMetadata", 0x2010, None),
        ]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["format"], "pe")
        self.assertEqual(report["machine"], "amd64")
        self.assertEqual(report["bits"], 64)
        self.assertEqual(report["export_count"], 2)
        self.assertEqual(report["exports"], [
            {"ordinal": 1, "name": "FxDriverEntryUm", "rva": 0x2000, "forwarder": None},
            {"ordinal": 2, "name": "__ImagePolicyMetadata", "rva": 0x2010, "forwarder": None},
        ])

    def test_ordinal_gap_has_null_name(self) -> None:
        proc = self.run_tool(build_pe([
            ("first", 0x2000, None),
            (None, 0x2010, None),
            ("third", 0x2020, None),
        ]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual([row["ordinal"] for row in report["exports"]], [1, 2, 3])
        self.assertEqual([row["name"] for row in report["exports"]], ["first", None, "third"])

    def test_forwarded_export(self) -> None:
        proc = self.run_tool(build_pe([
            (None, 0x2000, "other.Module.Target"),
        ]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["exports"][0]["forwarder"], "other.Module.Target")
        self.assertNotEqual(report["exports"][0]["rva"], 0x2000)

    def test_no_export_directory(self) -> None:
        proc = self.run_tool(build_pe([], export_rva=None))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["exports"], [])

    def test_malformed_images_fail_closed(self) -> None:
        for data in (
            b"MZ" + b"\0" * 10,
            build_pe([("x", 0x2000, None)], export_rva=0x9000),
        ):
            with self.subTest(size=len(data)):
                proc = self.run_tool(data)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertIn("wsm_pe_exports:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
