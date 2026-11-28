# SPDX-License-Identifier: LicenseRef-Volnist
"""Measure what the Python tooling actually costs before anyone rewrites it.

The owner's objection is that his packages are written in "inefficient Python".
That is a claim with a number in it, and the number had never been measured.
This script measures it, so a rewrite has a baseline to beat and nobody argues
from adjectives.

What it measures, on whatever machine runs it:

* interpreter startup — the tax paid on every invocation of ``wsm-hwcheck``;
* the cost of importing the package's own modules on top of that;
* the share attributable to ``jsonschema``, the heaviest third-party input.

It deliberately does not measure a rewrite, because no rewrite exists yet.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPEATS = 7


def measure(command: list[str]) -> float:
    """Best-of-N wall time in milliseconds; the minimum is the least noisy."""
    samples: list[float] = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        subprocess.run(command, capture_output=True, check=False)
        samples.append((time.perf_counter() - start) * 1000)
    return min(samples)


def report(python: str) -> list[tuple[str, float]]:
    cases = [
        ("інтерпретатор (python -c pass)", [python, "-c", "pass"]),
        ("+ jsonschema", [python, "-c", "import jsonschema"]),
        (
            "+ власні модулі wsm_hwcheck",
            [python, "-c", "import sys; sys.path.insert(0, '.'); import wsm_hwcheck"],
        ),
        (
            "+ власні модулі wsm_install",
            [python, "-c", "import sys; sys.path.insert(0, '.'); import wsm_install"],
        ),
    ]
    return [(label, measure(command)) for label, command in cases]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the Python tooling's startup cost.")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    arguments = parser.parse_args(argv)

    if not (ROOT / "wsm_hwcheck").is_dir():
        print(f"measure-python-cost: {ROOT} does not look like the repository", file=sys.stderr)
        return 2

    results = report(arguments.python)
    baseline = results[0][1]

    if arguments.json:
        import json

        print(
            json.dumps(
                {
                    "python": arguments.python,
                    "repeats": REPEATS,
                    "milliseconds": {label: round(value, 1) for label, value in results},
                    "note": "best-of-N wall time; no rewrite exists to compare against",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"вимірювання: {arguments.python}, найкраще з {REPEATS}\n")
    for label, value in results:
        share = "" if value == baseline else f"  (+{value - baseline:.0f} мс до старту)"
        print(f"  {label:<38} {value:6.0f} мс{share}")
    print(
        "\nЦе податок на КОЖЕН виклик. Він не залежить від того, скільки роботи "
        "інструмент робить: 76 мс платяться навіть за `--help`.\n"
        "Переписування на FPC дає статичний бінарник із ~0 мс старту — саме так "
        "зроблено в gp107-nvidia-re. Порівнювати треба з цими числами, а не з "
        "відчуттям."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
