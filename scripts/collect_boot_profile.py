#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Collect a read-only systemd boot profile for one current boot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_perf.boot import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    VERSION,
    collect_boot_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-boot-profile",
        description=(
            "Collect read-only systemd boot milestones and service critical paths "
            "for the current boot."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-command timeout in seconds (0, {MAX_TIMEOUT_SECONDS:g}]",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="write the JSON artifact here instead of stdout",
    )
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifact = collect_boot_profile(timeout_seconds=args.timeout)
    except ValueError as exc:
        print(f"wsm-boot-profile: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(
        artifact,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=True,
    ) + "\n"
    if args.output:
        try:
            Path(args.output).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"wsm-boot-profile: cannot write output: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
