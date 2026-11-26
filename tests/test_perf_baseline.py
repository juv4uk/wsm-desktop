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
import wsm_perf.pressure as pressure  # noqa: E402

from measure_baseline import (  # noqa: E402
    NOISE_THRESHOLD,
    WORKLOADS,
    environment,
    measure,
    median_and_spread,
)


EMPTY_PRESSURE_SNAPSHOT = {"psi": {}, "zram": {"status": "unavailable", "devices": {}}}


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


class PressureTelemetryTests(unittest.TestCase):
    def test_parse_psi_keeps_some_and_full_with_microsecond_totals(self) -> None:
        parsed = pressure.parse_psi(
            "some avg10=1.25 avg60=0.80 avg300=0.30 total=1000\n"
            "full avg10=0.12 avg60=0.10 avg300=0.02 total=250\n"
        )
        self.assertEqual(parsed["some"]["total"], 1000)
        self.assertEqual(parsed["full"]["total"], 250)
        self.assertEqual(parsed["some"]["avg10"], 1.25)

    def test_parse_psi_accepts_cpu_some_without_full(self) -> None:
        parsed = pressure.parse_psi(
            "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        )
        self.assertEqual(set(parsed), {"some"})

    def test_parse_psi_rejects_incomplete_or_out_of_range_fields(self) -> None:
        with self.assertRaises(ValueError):
            pressure.parse_psi("some avg10=0.1 total=10\n")
        with self.assertRaises(ValueError):
            pressure.parse_psi("some avg10=101 avg60=0 avg300=0 total=10\n")

    def test_read_psi_snapshot_distinguishes_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cpu").write_text(
                "some avg10=0 avg60=0 avg300=0 total=10\n", encoding="utf-8"
            )
            (root / "memory").write_text("not a PSI line\n", encoding="utf-8")
            snapshot = pressure.read_psi_snapshot(root)
        self.assertEqual(snapshot["cpu"]["status"], "available")
        self.assertEqual(snapshot["memory"]["reason"], "invalid-format")
        self.assertEqual(snapshot["io"]["reason"], "not-found")

    def test_parse_zram_stats_preserves_field_names_and_older_mm_layout(self) -> None:
        current = pressure.parse_zram_stat("100 50 60 1000 70 1 2 3 4", "mm_stat")
        older = pressure.parse_zram_stat("100 50 60 1000 70 1 2 3", "mm_stat")
        self.assertEqual(current["fields"]["huge_pages_since"], 4)
        self.assertEqual(older["status"], "partial")
        self.assertEqual(older["missing_fields"], ["huge_pages_since"])
        self.assertEqual(
            pressure.parse_zram_stat("1 2 3 4", "io_stat")["fields"]["failed_writes"],
            2,
        )

    def test_zram_snapshot_is_partial_when_config_source_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3 4\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            (device / "backing_dev").write_text("none\n", encoding="utf-8")
            # Missing comp_algorithm means the reported zram configuration is incomplete.
            snapshot = pressure.read_zram_snapshot(root)
        report = snapshot["devices"]["zram0"]
        self.assertEqual(snapshot["status"], "partial")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["config"]["status"], "partial")
        self.assertEqual(report["config"]["active_compressor"], "unknown")

    def test_read_zram_snapshot_is_read_only_and_records_active_compressor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3 4\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            (device / "comp_algorithm").write_text(
                "lzo [zstd] lz4\n", encoding="utf-8"
            )
            (device / "backing_dev").write_text("none\n", encoding="utf-8")
            snapshot = pressure.read_zram_snapshot(root)
            self.assertEqual(set(path.name for path in root.iterdir()), {"zram0"})
        self.assertEqual(snapshot["status"], "available")
        self.assertEqual(snapshot["devices"]["zram0"]["config"]["status"], "available")
        self.assertEqual(
            snapshot["devices"]["zram0"]["config"]["active_compressor"], "zstd"
        )
        self.assertEqual(
            snapshot["devices"]["zram0"]["config"]["backing_device"], "none"
        )
        self.assertEqual(
            snapshot["devices"]["zram0"]["stats"]["mm_stat"]["fields"]["orig_data_size"],
            100,
        )

    def test_empty_backing_device_value_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3 4\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            (device / "comp_algorithm").write_text("lzo [zstd] lz4\n", encoding="utf-8")
            (device / "backing_dev").write_text("\n", encoding="utf-8")
            snapshot = pressure.read_zram_snapshot(root)
        config = snapshot["devices"]["zram0"]["config"]
        self.assertEqual(config["backing_device"], "unknown")
        self.assertEqual(config["status"], "partial")

    def test_zram_snapshot_redacts_backing_device_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3 4\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            (device / "comp_algorithm").write_text("lzo [zstd] lz4\n", encoding="utf-8")
            (device / "backing_dev").write_text("/dev/nvme0n1p3\n", encoding="utf-8")
            snapshot = pressure.read_zram_snapshot(root)
        self.assertEqual(
            snapshot["devices"]["zram0"]["config"]["backing_device"], "configured"
        )
        self.assertNotIn("/dev/nvme0n1p3", str(snapshot))

    def test_zram_snapshot_is_partial_when_both_config_sources_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3 4\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            snapshot = pressure.read_zram_snapshot(root)
        device_result = snapshot["devices"]["zram0"]
        self.assertEqual(device_result["status"], "partial")
        self.assertEqual(device_result["config"]["status"], "partial")
        for stat_name in ("mm_stat", "io_stat", "bd_stat"):
            self.assertEqual(device_result["stats"][stat_name]["status"], "available")
        self.assertEqual(
            device_result["config"]["sources"]["comp_algorithm"]["reason"],
            "not-found",
        )
        self.assertEqual(
            device_result["config"]["sources"]["backing_dev"]["reason"],
            "not-found",
        )

    def test_mm_stat_stays_snapshot_while_io_and_bd_are_deltas(self) -> None:
        def stat(fields: dict[str, int]) -> dict[str, object]:
            return {"status": "available", "fields": fields}

        before = {
            "psi": {
                "memory": {
                    "status": "available",
                    "lines": {"some": {"total": 100}, "full": {"total": 50}},
                }
            },
            "zram": {
                "devices": {
                    "zram0": {
                        "status": "available",
                        "config": {
                            "status": "available",
                            "active_compressor": "zstd",
                            "backing_device": "none",
                        },
                        "stats": {
                            "mm_stat": stat({"orig_data_size": 100}),
                            "io_stat": stat({
                                "failed_reads": 1, "failed_writes": 2,
                                "invalid_io": 0, "notify_free": 3,
                            }),
                            "bd_stat": stat({"bd_count": 5, "bd_reads": 6, "bd_writes": 7}),
                        }
                    }
                }
            },
        }
        after = {
            "psi": {
                "memory": {
                    "status": "available",
                    "lines": {"some": {"total": 220}, "full": {"total": 70}},
                }
            },
            "zram": {
                "devices": {
                    "zram0": {
                        "status": "available",
                        "config": {
                            "status": "available",
                            "active_compressor": "zstd",
                            "backing_device": "none",
                        },
                        "stats": {
                            "mm_stat": stat({"orig_data_size": 150}),
                            "io_stat": stat({
                                "failed_reads": 3, "failed_writes": 3,
                                "invalid_io": 0, "notify_free": 4,
                            }),
                            "bd_stat": stat({"bd_count": 5, "bd_reads": 6, "bd_writes": 9}),
                        }
                    }
                }
            },
        }
        result = pressure.compare_pressure_snapshots(before, after)
        self.assertEqual(result["scope"], "system-wide")
        self.assertIn("do not attribute pressure", result["interpretation"])
        self.assertEqual(result["psi"]["memory"]["total_delta_us"]["some"], 120)
        self.assertEqual(
            result["zram"]["devices"]["zram0"]["counter_delta"]["io_stat"]["fields"]["failed_reads"],
            2,
        )
        self.assertEqual(
            result["zram"]["devices"]["zram0"]["counter_delta"]["bd_stat"]["fields"]["bd_writes"],
            2,
        )
        self.assertEqual(
            result["zram"]["devices"]["zram0"]["mm_stat"]["after"]["fields"]["orig_data_size"],
            150,
        )
        self.assertEqual(result["zram"]["devices"]["zram0"]["status"], "available")
        after["zram"]["devices"]["zram0"]["config"]["active_compressor"] = "lz4"
        changed = pressure.compare_pressure_snapshots(before, after)
        self.assertEqual(changed["zram"]["devices"]["zram0"]["status"], "partial")
        self.assertTrue(changed["zram"]["devices"]["zram0"]["config"]["changed"])

    def test_older_zram_mm_stat_keeps_snapshot_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "zram0"
            device.mkdir()
            (device / "mm_stat").write_text(
                "100 50 60 1000 70 1 2 3\n", encoding="utf-8"
            )
            (device / "io_stat").write_text("1 2 3 4\n", encoding="utf-8")
            (device / "bd_stat").write_text("5 6 7\n", encoding="utf-8")
            snapshot = pressure.read_zram_snapshot(root)
        self.assertEqual(snapshot["status"], "partial")
        self.assertEqual(snapshot["devices"]["zram0"]["status"], "partial")

        interval = pressure.compare_pressure_snapshots(
            {"psi": {}, "zram": snapshot},
            {"psi": {}, "zram": snapshot},
        )
        self.assertEqual(interval["zram"]["status"], "partial")
        self.assertEqual(interval["zram"]["devices"]["zram0"]["status"], "partial")

    def test_psi_line_set_change_is_partial_not_complete(self) -> None:
        before = {
            "psi": {"memory": {"status": "available", "lines": {
                "some": {"total": 10}, "full": {"total": 5}
            }}},
            "zram": {"devices": {}},
        }
        after = {
            "psi": {"memory": {"status": "available", "lines": {
                "some": {"total": 20}
            }}},
            "zram": {"devices": {}},
        }
        result = pressure.compare_pressure_snapshots(before, after)
        self.assertEqual(result["psi"]["memory"]["status"], "partial")

    def test_counter_reset_is_unknown_not_a_negative_event_count(self) -> None:
        before = {"status": "available", "fields": {"failed_reads": 10}}
        after = {"status": "available", "fields": {"failed_reads": 2}}
        result = pressure._counter_deltas(before, after)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["fields"]["failed_reads"])
        self.assertEqual(result["reason"], "counter-reset")

    def test_counter_field_set_change_is_partial(self) -> None:
        before = {
            "status": "available",
            "fields": {"failed_reads": 1, "failed_writes": 2},
        }
        after = {"status": "available", "fields": {"failed_reads": 3}}
        result = pressure._counter_deltas(before, after)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reason"], "field-set-changed")
        self.assertEqual(result["missing_after_fields"], ["failed_writes"])

    def test_missing_psi_and_zram_are_unknown_not_zero(self) -> None:
        result = pressure.compare_pressure_snapshots(
            EMPTY_PRESSURE_SNAPSHOT, EMPTY_PRESSURE_SNAPSHOT
        )
        self.assertEqual(result["psi"]["memory"]["status"], "unknown")
        self.assertEqual(result["zram"]["status"], "unavailable")
        self.assertEqual(result["psi"]["memory"]["total_delta_us"], {})


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

    @staticmethod
    def virtualization_report(value: str) -> dict[str, object]:
        return {
            "environment": {"virtualization": value},
            "collectors": [
                {"name": "wsm-hwcheck-sysfs", "version": "0.2.0"}
            ],
        }

    def test_physical_request_with_unknown_virtualization_is_not_confirmed(self) -> None:
        with patch.object(
            perf,
            "collect_report",
            return_value=self.virtualization_report("unknown"),
        ) as collector:
            artifact = environment("physical")
        collector.assert_called_once_with()
        self.assertEqual(artifact["mode"], "physical")
        self.assertEqual(artifact["detected_virtualization"], "unknown")
        self.assertEqual(artifact["mode_evidence"], "unknown")
        self.assertEqual(
            artifact["virtualization_source"], "wsm-hwcheck-sysfs/0.2.0"
        )

    def test_physical_request_with_qemu_evidence_is_a_mismatch(self) -> None:
        with patch.object(
            perf,
            "collect_report",
            return_value=self.virtualization_report("qemu"),
        ):
            artifact = environment("physical")
        self.assertEqual(artifact["detected_virtualization"], "qemu")
        self.assertEqual(artifact["mode_evidence"], "mismatch")

    def test_qemu_request_accepts_kvm_but_preserves_exact_detection(self) -> None:
        with patch.object(
            perf,
            "collect_report",
            return_value=self.virtualization_report("kvm"),
        ):
            artifact = environment("qemu")
        self.assertEqual(artifact["detected_virtualization"], "kvm")
        self.assertEqual(artifact["mode_evidence"], "consistent")

    def test_qemu_request_rejects_a_different_hypervisor(self) -> None:
        with patch.object(
            perf,
            "collect_report",
            return_value=self.virtualization_report("vmware"),
        ):
            artifact = environment("qemu")
        self.assertEqual(artifact["mode_evidence"], "mismatch")

    def test_missing_virtualization_field_remains_unknown(self) -> None:
        with patch.object(perf, "collect_report", return_value={}):
            artifact = environment("physical")
        self.assertEqual(artifact["detected_virtualization"], "unknown")
        self.assertEqual(artifact["mode_evidence"], "unknown")


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
        with (
            patch.dict(perf.WORKLOADS, synthetic),
            patch.object(perf, "read_pressure_snapshot", return_value=EMPTY_PRESSURE_SNAPSHOT),
        ):
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
        with (
            patch.dict(perf.WORKLOADS, synthetic),
            patch.object(perf, "read_pressure_snapshot", return_value=EMPTY_PRESSURE_SNAPSHOT),
        ):
            artifact = measure("physical", 5)
        self.assertEqual(set(artifact["workloads"]), names)
        for name, result in artifact["workloads"].items():
            with self.subTest(workload=name):
                self.assertGreater(result["median"], 0.0)

    def test_environment_does_not_guess_the_storage_class(self) -> None:
        self.assertEqual(environment("physical")["storage_class"], "unknown")

    def test_comparison_requires_consistent_virtualization_evidence(self) -> None:
        synthetic = {
            name: (lambda value=float(index + 1): value)
            for index, name in enumerate(WORKLOADS)
        }
        for detected, expected in (
            ("qemu", True),
            ("kvm", True),
            ("vmware", False),
            ("unknown", False),
        ):
            report = {
                "environment": {"virtualization": detected},
                "collectors": [
                    {"name": "wsm-hwcheck-sysfs", "version": "0.2.0"}
                ],
            }
            with self.subTest(detected=detected):
                with (
                    patch.object(perf, "collect_report", return_value=report),
                    patch.dict(perf.WORKLOADS, synthetic),
                    patch.object(perf, "read_pressure_snapshot", return_value=EMPTY_PRESSURE_SNAPSHOT),
                ):
                    artifact = measure("qemu", 5)
                self.assertEqual(artifact["comparison_eligible"], expected)
                self.assertEqual(
                    artifact["environment"]["detected_virtualization"], detected
                )

    def test_physical_comparison_is_not_eligible_without_bare_metal_evidence(self) -> None:
        synthetic = {
            name: (lambda value=float(index + 1): value)
            for index, name in enumerate(WORKLOADS)
        }
        report = {
            "environment": {"virtualization": "unknown"},
            "collectors": [
                {"name": "wsm-hwcheck-sysfs", "version": "0.2.0"}
            ],
        }
        with (
            patch.object(perf, "collect_report", return_value=report),
            patch.dict(perf.WORKLOADS, synthetic),
            patch.object(perf, "read_pressure_snapshot", return_value=EMPTY_PRESSURE_SNAPSHOT),
        ):
            artifact = measure("physical", 5)
        self.assertFalse(artifact["comparison_eligible"])
        self.assertEqual(artifact["environment"]["mode_evidence"], "unknown")

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
        with (
            patch.dict(perf.WORKLOADS, synthetic),
            patch.object(perf, "read_pressure_snapshot", return_value=EMPTY_PRESSURE_SNAPSHOT) as pressure,
        ):
            artifact = measure("qemu", 5)
        self.assertEqual(pressure.call_count, 2 * len(WORKLOADS))
        for result in artifact["workloads"].values():
            self.assertEqual(result["system_pressure"]["scope"], "system-wide")
            self.assertGreater(result["system_pressure"]["sample_window_seconds"], 0.0)
        self.assertEqual(calls, {name: 6 for name in calls})


if __name__ == "__main__":
    unittest.main()