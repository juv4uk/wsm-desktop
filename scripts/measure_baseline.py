# SPDX-License-Identifier: LicenseRef-Volnist
"""Measured performance baseline for WSM (issue #151).

Design rules, taken straight from the issue:

* numbers from a physical machine and from QEMU are never mixed - the mode is
  recorded and the artifact says what it may be compared with;
* every run records the environment that produced it (kernel, CPU, visible ISA
  level, memory, governor, storage class) because a number without it is
  useless;
* at least five repetitions, and the result is median with spread, not a mean
  of one lucky run;
* a run whose spread is wider than the noise threshold is flagged as noisy
  instead of being reported as a result.

The workloads are deliberately boring: integer arithmetic, memory traversal,
zlib compression, sha256, and a small synchronous write. They need no network,
no root and no external binary, so the same command works on a live image and
on a developer machine.

What this does not do: it does not claim WSM is fast. It produces evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_hwcheck.isa import IsaError, build_evidence, read_cpuinfo_flags  # noqa: E402

SCHEMA = "wsm-perf-baseline/1"
VERSION = "0.1.0"
DEFAULT_REPETITIONS = 5
# Above this relative spread a run is not a measurement, it is noise.
NOISE_THRESHOLD = 0.05
MODES = ("physical", "qemu")


def median_and_spread(samples: list[float]) -> dict[str, float]:
    """Median, p90 and MAD - the issue asks for spread, not a mean of one run."""
    ordered = sorted(samples)
    median = statistics.median(ordered)
    index = min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))
    p90 = ordered[index]
    mad = statistics.median([abs(value - median) for value in ordered])
    mad_relative = (mad / median) if median else 0.0
    p90_relative = ((p90 - median) / median) if median else 0.0
    # MAD alone hides an outlier when most samples are identical: with four
    # values at 1.0 and one at 2.0 the MAD is zero. The p90 deviation catches
    # exactly that shape, so a run is noisy when either measure is too wide.
    return {
        "median": median,
        "p90": p90,
        "mad": mad,
        "mad_relative": mad_relative,
        "p90_relative": p90_relative,
        "relative_spread": max(mad_relative, p90_relative),
        "samples": len(ordered),
        "noisy": max(mad_relative, p90_relative) > NOISE_THRESHOLD,
    }


def _workload_integer() -> float:
    total = 0
    for value in range(2_000_000):
        total += value * value % 7
    return float(total)


def _workload_memory() -> float:
    # 64 MiB, not 8: a workload that finishes in about a millisecond is
    # measuring the timer, not the machine. It showed up as a 700% spread.
    data = bytearray(64 * 1024 * 1024)
    for index in range(0, len(data), 4096):
        data[index] = index % 251
    return float(sum(data[::4096]))


def _workload_compress() -> float:
    # ~40 MiB of input: a few milliseconds is below the timer's own noise, and
    # the first version reported a 25% spread for that reason alone.
    payload = b"wsm-desktop baseline " * 2_000_000
    return float(len(zlib.compress(payload, 6)))


def _workload_hash() -> float:
    # ~60 MiB, for the same reason: 3 ms was measuring the clock.
    return float(hashlib.sha256(b"wsm" * 20_000_000).digest()[0])


def _workload_write() -> float:
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        path = Path(handle.name)
        handle.write(b"\0" * (64 * 1024 * 1024))
        handle.flush()
        os.fsync(handle.fileno())
    size = path.stat().st_size
    path.unlink()
    return float(size)


WORKLOADS: dict[str, Callable[[], float]] = {
    "integer_loop": _workload_integer,
    "memory_traversal": _workload_memory,
    "zlib_compress": _workload_compress,
    "sha256": _workload_hash,
    "sync_write": _workload_write,
}


def _read_first(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "unknown"


def environment(mode: str, cpuinfo_path: Path = Path("/proc/cpuinfo")) -> dict[str, Any]:
    """Everything a reader needs to decide whether two numbers may be compared."""
    meminfo = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if key in {"MemTotal", "SwapTotal"}:
                meminfo[key] = value.strip()
    except OSError:
        pass

    isa: dict[str, Any]
    cpu_model = "unknown"
    try:
        flags, fields = read_cpuinfo_flags(cpuinfo_path)
        cpu_model = fields.get("model name") or "unknown"
        isa = build_evidence(flags, fields, platform.machine(), f"procfs:{cpuinfo_path}")
    except IsaError as exc:
        isa = {"schema": None, "unavailable": exc.code, "message": exc.message}

    return {
        "mode": mode,
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_model": cpu_model,
        "isa_level": (isa.get("levels", {}) or {}).get("highest_supported", "unknown"),
        "memory": meminfo,
        "governor": _read_first(
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        ),
        # Storage class cannot be detected reliably from procfs; saying "unknown"
        # is honest, guessing "ssd" from a device name is not.
        "storage_class": "unknown",
        "guix_revision": os.environ.get("WSM_GUIX_REVISION", "unknown"),
    }


def measure(mode: str, repetitions: int) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if repetitions < 5:
        raise ValueError(
            "at least 5 repetitions are required; fewer cannot show spread"
        )

    results: dict[str, Any] = {}
    for name, workload in WORKLOADS.items():
        workload()  # warm-up, discarded: the first call pays for page faults
        samples: list[float] = []
        for _ in range(repetitions):
            started = time.perf_counter()
            workload()
            samples.append(time.perf_counter() - started)
        results[name] = median_and_spread(samples)

    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "environment": environment(mode),
        "repetitions": repetitions,
        "noise_threshold": NOISE_THRESHOLD,
        "workloads": results,
        "comparable_with": (
            "only runs with the same schema, the same mode and a recorded ISA level; "
            "QEMU/TCG numbers are not comparable with physical ones"
        ),
        "warnings": [
            workload
            for workload, result in results.items()
            if result["noisy"]
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-perf-baseline",
        description="Run low-noise baseline workloads and emit a versioned JSON artifact.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--mode", choices=MODES, required=True,
                        help="physical or qemu; recorded so the two are never mixed")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--output", metavar="PATH", help="write JSON here instead of stdout")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifact = measure(args.mode, args.repetitions)
    except ValueError as exc:
        print(f"wsm-perf-baseline: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(
        artifact, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
