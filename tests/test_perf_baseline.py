# SPDX-License-Identifier: LicenseRef-Volnist
"""Checks the measurement harness, not the machine's speed."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

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

    def test_p90_uses_nearest_rank_for_even_sample_counts(self) -> None:
        six = median_and_spread([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(six["p90"], 6.0)
        ten = median_and_spread([float(value) for value in range(1, 11)])
        self.assertEqual(ten["p90"], 9.0)

    def test_p90_is_within_range(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = median_and_spread(samples)
        self.assertGreaterEqual(result["p90"], result["median"])
        self.assertLessEqual(result["p90"], max(samples))


class MeasurementTests(unittest.TestCase):
    def test_fewer_than_five_repetitions_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            measure("physical", 3)

    def test_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            measure("vm", 5)

    def test_artifact_records_what_makes_it_comparable(self) -> None:
        artifact = measure("qemu", 5)
        self.assertEqual(artifact["schema"], "wsm-perf-baseline/1")
        self.assertEqual(artifact["mode"], "qemu")
        for field in ("kernel_release", "isa_level", "memory", "governor", "storage_class"):
            with self.subTest(field=field):
                self.assertIn(field, artifact["environment"])
        self.assertIn("not comparable", artifact["comparable_with"])

    def test_every_workload_produces_a_result(self) -> None:
        artifact = measure("physical", 5)
        self.assertEqual(set(artifact["workloads"]), set(WORKLOADS))
        for name, result in artifact["workloads"].items():
            with self.subTest(workload=name):
                self.assertGreater(result["median"], 0.0)

    def test_cpu_model_comes_from_the_model_name_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cpuinfo = Path(temporary) / "cpuinfo"
            cpuinfo.write_text(
                "processor : 0\\n"
                "vendor_id : GenuineIntel\\n"
                "model name : Intel(R) Core(TM) i5-6400 CPU @ 2.70GHz\\n"
                "flags : sse sse2\\n",
                encoding="utf-8",
            )
            artifact = environment("physical", cpuinfo_path=cpuinfo)
        self.assertEqual(artifact["environment"]["cpu_model"], "Intel(R) Core(TM) i5-6400 CPU @ 2.70GHz")

    def test_cpu_model_is_unknown_when_cpuinfo_is_unavailable(self) -> None:
        artifact = environment("physical", cpuinfo_path=Path("/definitely/missing/wsm-cpuinfo"))
        self.assertEqual(artifact["environment"]["cpu_model"], "unknown")

    def test_environment_does_not_guess_the_storage_class(self) -> None:
        self.assertEqual(environment("physical")["storage_class"], "unknown")


if __name__ == "__main__":
    unittest.main()
