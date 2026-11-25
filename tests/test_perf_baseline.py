# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks the measurement harness, not the machine's speed."""

from __future__ import annotations

import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_baseline as perf  # noqa: E402

from measure_baseline import (  # noqa: E402
    NOISE_THRESHOLD,
    WORKLOADS,
    environment,
    measure,
    median_and_spread,
)


class SpreadTests(unittest.TestCase):
    def test_median_is_not_a_mean_of_one_run(self) -> None:
        result = median_and_spread([1.0, 2.0, 3.0, 4.0, 100.0])
        self.assertEqual(result["median"], 3.0)
        self.assertEqual(result["samples"], 5)

    def test_identical_samples_are_not_noisy(self) -> None:
        result = median_and_spread([2.0, 2.0, 2.0, 2.0, 2.0])
        self.assertFalse(result["noisy"])
        self.assertEqual(result["mad"], 0.0)

    def test_wide_spread_is_flagged(self) -> None:
        result = median_and_spread([1.0, 1.0, 1.0, 1.0, 2.0])
        self.assertTrue(result["noisy"])
        self.assertGreater(result["relative_spread"], NOISE_THRESHOLD)

    def test_p90_uses_nearest_rank_for_default_and_other_repetitions(self) -> None:
        five = median_and_spread([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(five["p90"], 5.0)
        self.assertEqual(five["p90_method"], "nearest-rank")
        self.assertEqual(five["p90_rank"], 5)
        ten = median_and_spread([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        self.assertEqual(ten["p90"], 9.0)
        self.assertEqual(ten["p90_rank"], 9)
        six = median_and_spread([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(six["p90"], 6.0)
        self.assertEqual(six["p90_rank"], 6)
        seven = median_and_spread([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        self.assertEqual(seven["p90"], 7.0)
        self.assertEqual(seven["p90_rank"], 7)

    def test_p90_is_within_range(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = median_and_spread(samples)
        self.assertGreaterEqual(result["p90"], result["median"])
        self.assertLessEqual(result["p90"], max(samples))


class EnvironmentProvenanceTests(unittest.TestCase):
    @staticmethod
    def write_cpuinfo(directory: str, *, include_model: bool = True) -> Path:
        cpuinfo = Path(directory) / "cpuinfo"
        lines = [
            "processor : 0",
            "vendor_id : GenuineIntel",
        ]
        if include_model:
            lines.append("model name : Intel(R) Core(TM) i5-6400 CPU @ 2.70GHz")
        lines.append("flags : sse sse2")
        cpuinfo.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return cpuinfo

    def test_cpu_model_uses_the_actual_model_name_field(self) -> None:
        expected = "Intel(R) Core(TM) i5-6400 CPU @ 2.70GHz"
        with tempfile.TemporaryDirectory() as directory:
            cpuinfo = self.write_cpuinfo(directory)
            with patch.object(perf.platform, "machine", return_value="x86_64"):
                artifact = environment("physical", cpuinfo_path=cpuinfo)
        self.assertEqual(artifact["cpu_model"], expected)

    def test_missing_cpu_model_remains_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cpuinfo = self.write_cpuinfo(directory, include_model=False)
            with patch.object(perf.platform, "machine", return_value="x86_64"):
                artifact = environment("qemu", cpuinfo_path=cpuinfo)
        self.assertEqual(artifact["cpu_model"], "unknown")

    def test_unreadable_cpuinfo_leaves_model_unknown(self) -> None:
        with patch.object(perf.platform, "machine", return_value="x86_64"):
            artifact = environment(
                "qemu", cpuinfo_path=Path("/definitely/missing/wsm-cpuinfo")
            )
        self.assertEqual(artifact["cpu_model"], "unknown")


class SyncWriteCleanupTests(unittest.TestCase):
    def test_sync_write_removes_temporary_file_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(perf.tempfile, "tempdir", directory),
                patch.object(perf, "SYNC_WRITE_BYTES", 4096),
            ):
                written = perf._workload_write()
            self.assertEqual(written, 4096.0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_sync_write_removes_temporary_file_when_fsync_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(perf.tempfile, "tempdir", directory),
                patch.object(perf, "SYNC_WRITE_BYTES", 4096),
                patch.object(perf.os, "fsync", side_effect=OSError("synthetic fsync failure")),
            ):
                with self.assertRaisesRegex(OSError, "synthetic fsync failure"):
                    perf._workload_write()
            self.assertEqual(list(Path(directory).iterdir()), [])


class MeasurementTests(unittest.TestCase):
    def test_fewer_than_five_repetitions_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            measure("physical", 3)

    def test_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            measure("vm", 5)

    def test_artifact_records_what_makes_it_comparable(self) -> None:
        # Unit tests validate artifact construction, not the real benchmark load.
        synthetic = {
            name: (lambda value=float(index + 1): value)
            for index, name in enumerate(WORKLOADS)
        }
        with patch.dict(perf.WORKLOADS, synthetic):
            artifact = measure("qemu", 5)
        self.assertEqual(artifact["schema"], "wsm-perf-baseline/1")
        self.assertEqual(artifact["mode"], "qemu")
        for field in ("kernel_release", "isa_level", "memory", "governor", "storage_class"):
            with self.subTest(field=field):
                self.assertIn(field, artifact["environment"])
        self.assertIn("not comparable", artifact["comparable_with"])

    def test_every_workload_produces_a_result(self) -> None:
        names = set(WORKLOADS)
        synthetic = {
            name: (lambda value=float(index + 1): value)
            for index, name in enumerate(sorted(names))
        }
        with patch.dict(perf.WORKLOADS, synthetic):
            artifact = measure("physical", 5)
        self.assertEqual(set(artifact["workloads"]), names)
        for name, result in artifact["workloads"].items():
            with self.subTest(workload=name):
                self.assertGreater(result["median"], 0.0)

    def test_environment_does_not_guess_the_storage_class(self) -> None:
        self.assertEqual(environment("physical")["storage_class"], "unknown")

    def test_measure_runs_one_warmup_plus_each_requested_sample(self) -> None:
        calls = {name: 0 for name in WORKLOADS}

        def tracked(name: str, value: float):
            def run() -> float:
                calls[name] += 1
                return value
            return run

        synthetic = {
            name: tracked(name, float(index + 1))
            for index, name in enumerate(WORKLOADS)
        }
        with patch.dict(perf.WORKLOADS, synthetic):
            measure("qemu", 5)
        self.assertEqual(calls, {name: 6 for name in calls})


if __name__ == "__main__":
    unittest.main()