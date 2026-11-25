# SPDX-License-Identifier: LicenseRef-Volnist
"""Tests for the x86-64 micro-architecture level evidence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_hwcheck.isa import IsaError, evaluate, read_cpuinfo_flags  # noqa: E402

V2 = ["cx16", "lahf_lm", "popcnt", "pni", "ssse3", "sse4_1", "sse4_2"]
V3 = V2 + ["avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "osxsave"]
V4 = V3 + ["avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"]


class LevelEvaluationTests(unittest.TestCase):
    def test_baseline_has_no_level(self) -> None:
        result = evaluate(["sse", "sse2"], "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v1")
        self.assertFalse(result["x86-64-v2"]["supported"])

    def test_v2_needs_every_feature(self) -> None:
        incomplete = [feature for feature in V2 if feature != "popcnt"]
        result = evaluate(incomplete, "x86_64")
        self.assertFalse(result["x86-64-v2"]["supported"])
        self.assertEqual(result["x86-64-v2"]["missing"], ["popcnt"])

    def test_v2_reported_when_complete(self) -> None:
        result = evaluate(V2, "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v2")
        self.assertFalse(result["x86-64-v3"]["supported"])

    def test_avx_without_avx2_is_v2_not_almost_v3(self) -> None:
        """The psABI rule that surprises people: partial v3 is still v2."""
        result = evaluate(V2 + ["avx", "f16c", "fma"], "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v2")
        self.assertIn("avx2", result["x86-64-v3"]["missing"])

    def test_v3_reported_when_complete(self) -> None:
        result = evaluate(V3, "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v3")
        self.assertFalse(result["x86-64-v4"]["supported"])

    def test_v4_reported_when_complete(self) -> None:
        result = evaluate(V4, "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v4")
        self.assertEqual(result["x86-64-v4"]["missing"], [])

    def test_v4_without_lower_level_is_not_claimed(self) -> None:
        """Levels are cumulative: AVX-512 flags alone do not make a machine v4."""
        result = evaluate(V4[-5:], "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v1")

    def test_non_x86_architecture_is_refused(self) -> None:
        with self.assertRaises(IsaError) as caught:
            evaluate(V4, "aarch64")
        self.assertEqual(caught.exception.code, "isa.not-x86")


class OwnerHardwareTests(unittest.TestCase):
    """Skylake i5-6400 from wsm-os/docs/OWNER-HARDWARE-PROFILE.md.

    The owner's machine reports AVX2, FMA and BMI2 but no AVX-512, so it is v3
    by construction and can never be v4. Encoding that here stops a future
    change from quietly claiming more than the hardware has.
    """

    SKYLAKE = V3 + ["adx", "aes", "pclmulqdq", "rdrand", "rdseed", "vmx", "smep", "smap", "pcid"]

    def test_skylake_i5_6400_is_v3(self) -> None:
        result = evaluate(self.SKYLAKE, "x86_64")
        self.assertEqual(result["highest_supported"], "x86-64-v3")

    def test_skylake_is_not_v4(self) -> None:
        result = evaluate(self.SKYLAKE, "x86_64")
        self.assertFalse(result["x86-64-v4"]["supported"])
        self.assertIn("avx512f", result["x86-64-v4"]["missing"])

    def test_skylake_qualifies_for_v2_and_v3(self) -> None:
        result = evaluate(self.SKYLAKE, "x86_64")
        self.assertTrue(result["x86-64-v2"]["supported"])
        self.assertTrue(result["x86-64-v3"]["supported"])


class CpuinfoParsingTests(unittest.TestCase):
    def write(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".cpuinfo", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        return Path(handle.name)

    def test_reads_first_processor_block_only(self) -> None:
        path = self.write(
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Test CPU\n"
            "flags\t\t: " + " ".join(V3) + "\n"
            "\n"
            "processor\t: 1\n"
            "flags\t\t: sse sse2\n"
        )
        flags, fields = read_cpuinfo_flags(path)
        self.assertIn("avx2", flags)
        self.assertEqual(fields["vendor_id"], "GenuineIntel")
        path.unlink()

    def test_missing_cpuinfo_is_a_clean_refusal(self) -> None:
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(Path("/nonexistent/cpuinfo"))
        self.assertEqual(caught.exception.code, "cpuinfo.unreadable")


if __name__ == "__main__":
    unittest.main()
