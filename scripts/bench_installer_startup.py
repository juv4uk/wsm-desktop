# SPDX-License-Identifier: LicenseRef-Volnist
"""Measure what the installer costs to start, so the cost can be argued with numbers.

The installer runs on a 2 GB machine from a live medium. Every invocation pays for the
interpreter and for whatever the entry point imports, and that price is invisible until
someone measures it: `wsm-install --help` once took 481 ms because a JSON-schema
validator was imported at module scope for a command that never validates anything.

This script measures, in milliseconds, the median of several runs:

    the interpreter floor      python3 -c pass
    the entry point import     python3 -c 'import wsm_install.cli'
    the real command           python3 -m wsm_install --version

and, when given `--compare PATH`, the same three for another executable, so a compiled
candidate can be judged against the current one instead of against a feeling.

It reports; it never fails a build on a slow number. A threshold nobody agreed to is
how a measurement turns into a flaky gate.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(command: list[str], runs: int, cwd: Path) -> dict[str, float]:
    """Median wall-clock milliseconds for `command`, and the fastest run."""
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        result = subprocess.run(command, cwd=str(cwd), capture_output=True)
        elapsed = (time.perf_counter() - started) * 1000
        if result.returncode != 0:
            raise SystemExit(
                f"command failed ({result.returncode}): {' '.join(command)}\n"
                f"{result.stderr.decode('utf-8', 'replace')[:400]}"
            )
        samples.append(elapsed)
    return {
        "median_ms": round(statistics.median(samples), 1),
        "min_ms": round(min(samples), 1),
        "runs": runs,
    }


def python_costs(runs: int) -> dict[str, dict[str, float]]:
    return {
        "interpreter floor": measure([sys.executable, "-c", "pass"], runs, ROOT),
        "entry point import": measure(
            [sys.executable, "-c", "import wsm_install.cli"], runs, ROOT
        ),
        "wsm-install --version": measure(
            [sys.executable, "-m", "wsm_install", "--version"], runs, ROOT
        ),
    }


def compiled_costs(path: Path, runs: int) -> dict[str, dict[str, float]]:
    return {"compiled candidate": measure([str(path), "--version"], runs, ROOT)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=7, help="samples per measurement")
    parser.add_argument(
        "--compare",
        type=Path,
        help="an executable to measure against the Python entry point",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.runs < 3:
        parser.error("--runs below 3 is noise, not a measurement")

    report: dict[str, object] = {"python": python_costs(args.runs)}
    if args.compare is not None:
        if not args.compare.is_file():
            parser.error(f"--compare {args.compare} is not a file")
        report["compiled"] = compiled_costs(args.compare, args.runs)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for group, measurements in report.items():
        print(f"{group}:")
        for name, numbers in measurements.items():  # type: ignore[union-attr]
            print(f"  {name:26s} median {numbers['median_ms']:7.1f} ms   "
                  f"min {numbers['min_ms']:7.1f} ms")
    print()
    print("A compiled candidate is worth judging on the 'wsm-install --version' row:")
    print("the interpreter floor is what it removes, the import cost is what it moves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
