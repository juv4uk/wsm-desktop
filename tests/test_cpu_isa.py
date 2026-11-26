# SPDX-License-Identifier: LicenseRef-Volnist
"""Tests for x86-64 ISA evidence and conservative procfs aggregation."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_hwcheck.isa import (  # noqa: E402
    IsaError,
    build_evidence,
    evaluate,
    main,
    read_cpuinfo_flags,
)

V2 = ["cx16", "lahf_lm", "popcnt", "pni", "ssse3", "sse4_1", "sse4_2"]
V3 = V2 + ["avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "osxsave"]
V4 = V3 + ["avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"]


class LevelEvaluationTests(unittest.TestCase):
    def test_baseline_has_no_additional_level_evidence(self) -> None:
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
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".cpuinfo", delete=False, encoding="utf-8"
        )
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        handle.write(text)
        handle.close()
        return Path(handle.name)

    def test_uses_intersection_across_all_processor_blocks(self) -> None:
        path = self.write(
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Test CPU\n"
            "flags\t\t: " + " ".join(V3) + "\n"
            "\n"
            "processor\t: 1\n"
            "flags\t\t: " + " ".join(V2) + "\n"
        )
        flags, fields = read_cpuinfo_flags(path)
        self.assertEqual(set(flags), set(V2))
        self.assertEqual(fields["vendor_id"], "GenuineIntel")
        self.assertEqual(fields["logical_processor_count"], "2")

        evidence = build_evidence(flags, fields, "x86_64", "fixture")
        self.assertEqual(evidence["levels"]["highest_supported"], "x86-64-v2")
        self.assertEqual(evidence["evidence"]["logical_processor_count"], 2)
        self.assertEqual(evidence["evidence"]["scope"], "common-kernel-exposed-flags")

    def test_duplicate_flags_are_deduplicated(self) -> None:
        duplicated = V2 + V2 + ["avx"]
        path = self.write(
            "processor\t: 0\n"
            "flags\t: " + " ".join(duplicated) + "\n"
        )
        flags, _ = read_cpuinfo_flags(path)
        self.assertEqual(len(flags), len(set(flags)))
        self.assertEqual(set(flags), set(V2 + ["avx"]))

    def test_missing_flags_on_any_processor_is_a_clean_refusal(self) -> None:
        path = self.write(
            "processor\t: 0\n"
            "flags\t: " + " ".join(V3) + "\n"
            "\n"
            "processor\t: 1\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Test CPU\n"
        )
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(path)
        self.assertEqual(caught.exception.code, "cpuinfo.flags-incomplete")

    def test_missing_flags_on_every_processor_is_unavailable(self) -> None:
        path = self.write(
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "\n"
            "processor\t: 1\n"
            "vendor_id\t: GenuineIntel\n"
        )
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(path)
        self.assertEqual(caught.exception.code, "cpuinfo.flags-unavailable")

    def test_empty_flags_value_is_unavailable(self) -> None:
        path = self.write("processor\t: 0\nflags\t:\n")
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(path)
        self.assertEqual(caught.exception.code, "cpuinfo.flags-unavailable")

    def test_empty_cpuinfo_is_a_clean_refusal(self) -> None:
        path = self.write("")
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(path)
        self.assertEqual(caught.exception.code, "cpuinfo.empty")

    def test_mixed_malformed_block_is_not_silently_ignored(self) -> None:
        path = self.write(
            "processor\t: 0\n"
            "flags\t: " + " ".join(V3) + "\n"
            "\n"
            "flags\t: " + " ".join(V2) + "\n"
        )
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(path)
        self.assertEqual(caught.exception.code, "cpuinfo.processor-block-incomplete")

    def test_single_block_without_processor_key_keeps_fixture_fallback(self) -> None:
        path = self.write(
            "vendor_id: GenuineIntel\n"
            "flags: " + " ".join(V2) + "\n"
        )
        flags, fields = read_cpuinfo_flags(path)
        self.assertEqual(set(flags), set(V2))
        self.assertEqual(fields["logical_processor_count"], "1")
    def test_missing_cpuinfo_is_a_clean_refusal(self) -> None:
        with self.assertRaises(IsaError) as caught:
            read_cpuinfo_flags(Path("/nonexistent/cpuinfo"))
        self.assertEqual(caught.exception.code, "cpuinfo.unreadable")

    def test_cli_rejects_non_x86_before_reading_x86_procfs(self) -> None:
        stderr = io.StringIO()
        with patch("wsm_hwcheck.isa.host_platform.machine", return_value="aarch64"):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    main(["--cpuinfo", "/nonexistent/cpuinfo"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("isa.not-x86", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
