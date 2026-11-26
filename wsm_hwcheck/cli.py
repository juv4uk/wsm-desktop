# SPDX-License-Identifier: LicenseRef-Volnist
"""Command-line entry point for python -m wsm_hwcheck."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collector import VERSION, collect_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-hwcheck",
        description="Collect a local-only, read-only Linux hardware and driver/firmware evidence report.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--sysfs-root", default="/sys", help=argparse.SUPPRESS)
    parser.add_argument("--proc-root", default="/proc", help=argparse.SUPPRESS)
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="write the JSON report to this path; stdout is used when omitted",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    parser.add_argument(
        "--no-runtime-diagnostics",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = collect_report(
            args.sysfs_root,
            args.proc_root,
            include_runtime_diagnostics=not args.no_runtime_diagnostics,
        )
        rendered = json.dumps(
            report,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        ) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except OSError as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
