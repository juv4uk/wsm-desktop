# SPDX-License-Identifier: LicenseRef-Volnist
"""Runtime parity tests for the native wsm-cpu-isa executable."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pascal"
SOURCE = SOURCE_DIR / "wsm_cpu_isa.pas"

V2 = ["cx16", "lahf_lm", "popcnt", "pni", "ssse3", "sse4_1", "sse4_2"]
V3 = V2 + ["avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "osxsave"]
V4 = V3 + ["avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"]
SKYLAKE = V3 + ["adx", "aes", "pclmulqdq", "rdrand", "rdseed", "vmx", "smep", "smap", "pcid"]


@unittest.skipUnless(shutil.which("fpc"), "FPC is installed in the dedicated native build workflow")
class FpcCpuIsaRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="wsm-cpu-isa-test-")
        cls.build_dir = Path(cls.temporary.name)
        cls.binary = cls.build_dir / "wsm-cpu-isa"
        result = subprocess.run(
            [
                shutil.which("fpc") or "fpc",
                "-B",
                "-O2",
                "-Mobjfpc",
                "-Sh",
                f"-Fu{SOURCE_DIR}",
                f"-FU{cls.build_dir}",
                f"-FE{cls.build_dir}",
                f"-o{cls.binary}",
                str(SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not cls.binary.is_file():
            raise AssertionError(
                f"FPC CPU ISA build failed.\n{result.stdout}\n{result.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def cpuinfo(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="fixture-", dir=self.build_dir))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "cpuinfo"
        path.write_text(text, encoding="utf-8")
        return path

    def run_cpuinfo(self, text: str, *extra: str) -> subprocess.CompletedProcess[str]:
        path = self.cpuinfo(text)
        return subprocess.run(
            [str(self.binary), "--cpuinfo", str(path), "--architecture", "x86_64", "--compact", *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def evidence(self, text: str) -> dict:
        result = self.run_cpuinfo(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    @staticmethod
    def block(processor: int, flags: list[str], vendor: str = "GenuineIntel",
              model: str = "Test CPU") -> str:
        return (
            f"processor\t: {processor}\n"
            f"vendor_id\t: {vendor}\n"
            f"model name\t: {model}\n"
            f"flags\t\t: {' '.join(flags)}\n"
        )

    def test_baseline_has_no_additional_level_evidence(self) -> None:
        result = self.evidence(self.block(0, ["sse", "sse2"]))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v1")
        self.assertFalse(result["levels"]["x86-64-v2"]["supported"])

    def test_v2_needs_every_feature_and_reports_missing_names(self) -> None:
        flags = [feature for feature in V2 if feature != "popcnt"]
        result = self.evidence(self.block(0, flags))
        self.assertFalse(result["levels"]["x86-64-v2"]["supported"])
        self.assertEqual(result["levels"]["x86-64-v2"]["missing"], ["popcnt"])

    def test_v2_level_is_supported_when_complete(self) -> None:
        result = self.evidence(self.block(0, V2))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v2")
        self.assertTrue(result["levels"]["x86-64-v2"]["supported"])
        self.assertFalse(result["levels"]["x86-64-v3"]["supported"])

    def test_partial_v3_does_not_become_v3(self) -> None:
        result = self.evidence(self.block(0, V2 + ["avx", "f16c", "fma"]))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v2")
        self.assertIn("avx2", result["levels"]["x86-64-v3"]["missing"])

    def test_v3_level_is_supported_when_complete(self) -> None:
        result = self.evidence(self.block(0, V3))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v3")
        self.assertFalse(result["levels"]["x86-64-v4"]["supported"])

    def test_v4_level_is_supported_when_complete(self) -> None:
        result = self.evidence(self.block(0, V4))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v4")
        self.assertEqual(result["levels"]["x86-64-v4"]["missing"], [])

    def test_v4_flags_without_lower_levels_do_not_claim_v4(self) -> None:
        result = self.evidence(self.block(0, V4[-5:]))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v1")
        self.assertFalse(result["levels"]["x86-64-v4"]["supported"])

    def test_owner_skylake_i5_6400_is_v3_and_not_v4(self) -> None:
        result = self.evidence(self.block(0, SKYLAKE))
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v3")
        self.assertTrue(result["levels"]["x86-64-v2"]["supported"])
        self.assertTrue(result["levels"]["x86-64-v3"]["supported"])
        self.assertFalse(result["levels"]["x86-64-v4"]["supported"])
        self.assertIn("avx512f", result["levels"]["x86-64-v4"]["missing"])

    def test_flags_are_intersected_across_all_processors(self) -> None:
        text = self.block(0, V3) + "\n" + self.block(1, V2)
        result = self.evidence(text)
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v2")
        self.assertEqual(result["evidence"]["logical_processor_count"], 2)
        self.assertEqual(result["evidence"]["feature_count"], len(V2))

    def test_empty_intersection_stays_empty_for_later_processors(self) -> None:
        text = (
            self.block(0, ["sse", "sse2"])
            + "\n" + self.block(1, ["avx", "avx2"])
            + "\n" + self.block(2, V3)
        )
        result = self.evidence(text)
        self.assertEqual(result["evidence"]["feature_count"], 0)
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v1")

    def test_duplicate_flags_are_deduplicated(self) -> None:
        result = self.evidence(self.block(0, V2 + V2 + ["avx"]))
        self.assertEqual(result["evidence"]["feature_count"], len(set(V2 + ["avx"])))

    def test_missing_flags_on_one_processor_is_refused(self) -> None:
        text = self.block(0, V3) + "\n" + (
            "processor\t: 1\nvendor_id\t: GenuineIntel\nmodel name\t: Test CPU\n"
        )
        result = self.run_cpuinfo(text)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.flags-incomplete", result.stderr)

    def test_missing_flags_on_every_processor_is_unavailable(self) -> None:
        text = (
            "processor\t: 0\nvendor_id\t: GenuineIntel\n\n"
            "processor\t: 1\nvendor_id\t: GenuineIntel\n"
        )
        result = self.run_cpuinfo(text)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.flags-unavailable", result.stderr)

    def test_empty_flags_value_is_unavailable(self) -> None:
        result = self.run_cpuinfo("processor\t: 0\nflags\t:\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.flags-unavailable", result.stderr)

    def test_empty_cpuinfo_is_refused(self) -> None:
        result = self.run_cpuinfo("")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.empty", result.stderr)

    def test_malformed_mixed_block_is_not_ignored(self) -> None:
        text = self.block(0, V3) + "\n" + "flags: " + " ".join(V2) + "\n"
        result = self.run_cpuinfo(text)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.processor-block-incomplete", result.stderr)

    def test_single_block_without_processor_key_uses_fixture_fallback(self) -> None:
        text = "vendor_id: GenuineIntel\nflags: " + " ".join(V2) + "\n"
        result = self.evidence(text)
        self.assertEqual(result["levels"]["highest_supported"], "x86-64-v2")
        self.assertEqual(result["evidence"]["logical_processor_count"], 1)

    def test_non_x86_architecture_is_refused_before_reading_cpuinfo(self) -> None:
        missing = Path(self.build_dir) / "not-present"
        result = subprocess.run(
            [str(self.binary), "--cpuinfo", str(missing), "--architecture", "aarch64"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("isa.not-x86", result.stderr)
        self.assertNotIn("cpuinfo.unreadable", result.stderr)

    def test_missing_cpuinfo_is_a_clean_refusal(self) -> None:
        missing = Path(self.build_dir) / "not-present"
        result = subprocess.run(
            [str(self.binary), "--cpuinfo", str(missing), "--architecture", "x86_64"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("cpuinfo.unreadable", result.stderr)

    def test_unexpected_vendor_and_missing_osxsave_are_warnings(self) -> None:
        result = self.evidence(self.block(0, V2, vendor="ExampleVendor"))
        self.assertTrue(any("unexpected vendor_id" in item for item in result["warnings"]))
        self.assertTrue(any("osxsave" in item for item in result["warnings"]))

    def test_output_contract_and_version(self) -> None:
        result = self.evidence(self.block(0, V2))
        self.assertEqual(result["schema"], "wsm-cpu-isa/1")
        self.assertEqual(result["tool_version"], "0.1.2")
        self.assertEqual(result["architecture"], "x86_64")
        self.assertEqual(result["vendor"], "GenuineIntel")
        self.assertEqual(result["model_name"], "Test CPU")
        self.assertEqual(result["evidence"]["scope"], "common-kernel-exposed-flags")
        self.assertEqual(result["evidence"]["confidence"], "confirmed")
        self.assertEqual(result["evidence"]["kind"], "live-observation")
        self.assertTrue(result["collected_at"].endswith("Z"))

    def test_report_cross_check_preserves_identity_and_warns_on_other_architecture(self) -> None:
        cpuinfo = self.cpuinfo(self.block(0, V2))
        report_path = self.build_dir / "hardware-report.json"
        report_path.write_text(
            json.dumps({
                "report_id": "report-fixture-1",
                "schema_version": "1.1.0",
                "environment": {"architecture": "aarch64"},
            }),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                str(self.binary),
                "--cpuinfo", str(cpuinfo),
                "--architecture", "x86_64",
                "--report", str(report_path),
                "--compact",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["cross_check"],
            {
                "report_id": "report-fixture-1",
                "report_architecture": "aarch64",
                "report_schema_version": "1.1.0",
            },
        )
        self.assertTrue(any("differs from the running machine" in warning
                            for warning in output["warnings"]))

    def test_malformed_cross_check_report_is_refused(self) -> None:
        cpuinfo = self.cpuinfo(self.block(0, V2))
        report_path = self.build_dir / "broken-report.json"
        report_path.write_text("{broken", encoding="utf-8")
        result = subprocess.run(
            [
                str(self.binary),
                "--cpuinfo", str(cpuinfo),
                "--architecture", "x86_64",
                "--report", str(report_path),
                "--compact",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read report", result.stderr)

    def test_cli_help_and_version(self) -> None:
        help_result = subprocess.run(
            [str(self.binary), "--help"], capture_output=True, text=True, check=False
        )
        version_result = subprocess.run(
            [str(self.binary), "--version"], capture_output=True, text=True, check=False
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--cpuinfo PATH", help_result.stdout)
        self.assertIn("--report PATH", help_result.stdout)
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertEqual(version_result.stdout.strip(), "wsm-cpu-isa 0.1.2")


if __name__ == "__main__":
    unittest.main()
