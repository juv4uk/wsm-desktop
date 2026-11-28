# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime contract for the native Free Pascal CPU ISA evidence reader."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASCAL_DIR = ROOT / "tools" / "pascal"


class CpuIsaRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("WSM_CPU_ISA_FPC_BINARY")
        cls.temporary = None
        if supplied:
            candidate = Path(supplied)
            cls.program = candidate if candidate.is_absolute() else ROOT / candidate
            if not cls.program.is_file():
                raise AssertionError(f"FPC CPU ISA binary does not exist: {cls.program}")
            return
        if not shutil.which("fpc") or not shutil.which("make"):
            raise unittest.SkipTest("FPC is unavailable; CI supplies the native executable")
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-fpc-cpu-isa-")
        build_dir = Path(cls.temporary.name) / "build"
        completed = subprocess.run(
            ["make", "-C", str(PASCAL_DIR), f"BUILD_DIR={build_dir}", "wsm-cpu-isa"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "FPC CPU ISA build failed.\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        cls.program = build_dir / "wsm-cpu-isa"
        if not cls.program.is_file():
            raise AssertionError("FPC Makefile did not produce wsm-cpu-isa")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.temporary is not None:
            cls.temporary.cleanup()

    def run_reader(self, cpuinfo_text: str, architecture: str = "x86_64") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="wsm-cpuinfo-") as directory:
            cpuinfo = Path(directory) / "cpuinfo"
            cpuinfo.write_text(cpuinfo_text, encoding="utf-8")
            return subprocess.run(
                [str(self.program), "--compact", "--cpuinfo", str(cpuinfo),
                 "--architecture", architecture],
                capture_output=True,
                text=True,
                check=False,
            )

    @staticmethod
    def block(processor: int, flags: str) -> str:
        return (
            f"processor : {processor}\n"
            "vendor_id : GenuineIntel\n"
            "model name : Intel(R) Core(TM) fixture\n"
            f"flags : {flags}\n"
        )

    def test_levels_use_the_intersection_across_all_logical_processors(self) -> None:
        v2 = "cx16 lahf_lm popcnt pni ssse3 sse4_1 sse4_2"
        v3 = "avx avx2 bmi1 bmi2 f16c fma abm movbe osxsave"
        first = self.block(0, v2 + " " + v3)
        second = self.block(1, v2 + " " + v3.replace("avx2 ", ""))
        completed = self.run_reader(first + "\n" + second)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["schema"], "wsm-cpu-isa/1")
        self.assertEqual(payload["architecture"], "x86_64")
        self.assertEqual(payload["evidence"]["logical_processor_count"], 2)
        self.assertIs(payload["levels"]["x86-64-v2"]["supported"], True)
        self.assertIs(payload["levels"]["x86-64-v3"]["supported"], False)
        self.assertIn("avx2", payload["levels"]["x86-64-v3"]["missing"])
        self.assertEqual(payload["levels"]["highest_supported"], "x86-64-v2")

    def test_missing_flags_in_one_processor_block_is_refused(self) -> None:
        flags = "cx16 lahf_lm popcnt pni ssse3 sse4_1 sse4_2"
        incomplete = self.block(0, flags) + "\n" + (
            "processor : 1\n"
            "vendor_id : GenuineIntel\n"
            "model name : fixture without flags\n"
        )
        completed = self.run_reader(incomplete)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cpuinfo.flags-incomplete", completed.stderr)

    def test_non_x86_architecture_is_refused(self) -> None:
        completed = self.run_reader(self.block(0, "cx16"), "aarch64")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("isa.not-x86", completed.stderr)

    def test_version_is_available_without_reading_procfs(self) -> None:
        completed = subprocess.run(
            [str(self.program), "--version"], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("wsm-cpu-isa", completed.stdout)


if __name__ == "__main__":
    unittest.main()
