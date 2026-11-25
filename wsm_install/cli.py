# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only report validation, summary, and deterministic draft-plan output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .plan import build_plan, canonical_json, summarize_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-install",
        description="Validate a local WSM hardware report and draft a backend plan (read-only).",
    )
    parser.add_argument("--version", action="version", version="wsm-install 0.1.0")
    parser.add_argument("--preflight", action="store_true", help="run report preflight")
    parser.add_argument("--report", required=True, metavar="PATH", help="hardware report JSON")
    parser.add_argument("--backend", required=True, choices=("guix", "nix"))
    parser.add_argument("--dry-run", action="store_true", help="required; never deploys or writes disks")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help=argparse.SUPPRESS)
    parser.add_argument("--plan-output", metavar="PATH", help="write draft plan; stdout is used otherwise")
    parser.add_argument("--quiet", action="store_true", help="suppress human summary")
    return parser


def _load_json(path: Path) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, f"cannot read report: {exc}"
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, raw, f"invalid report JSON: {exc}"
    if not isinstance(value, dict):
        return None, raw, "invalid report JSON: top-level value must be an object"
    return value, raw, None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.preflight:
        parser.error("--preflight is required")
    if not args.dry_run:
        parser.error("--dry-run is required; this prototype never performs deployment")

    report, raw, error = _load_json(Path(args.report))
    if error:
        print(f"wsm-install: {error}", file=sys.stderr)
        return 2

    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"wsm-install: cannot load hardware report schema: {exc}", file=sys.stderr)
        return 2

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(report), key=lambda item: list(item.absolute_path))
    if errors:
        for item in errors[:20]:
            location = ".".join(str(part) for part in item.absolute_path) or "$"
            print(f"wsm-install: schema error at {location}: {item.message}", file=sys.stderr)
        if len(errors) > 20:
            print(f"wsm-install: {len(errors) - 20} additional schema errors omitted", file=sys.stderr)
        return 2

    assert raw is not None
    plan, blockers, warnings = build_plan(report, raw, args.backend)
    if not args.quiet:
        print(summarize_report(report), file=sys.stderr)
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        for blocker in blockers:
            print(f"BLOCKED: {blocker}", file=sys.stderr)

    if blockers:
        print("wsm-install: no plan emitted because required critical evidence is unresolved", file=sys.stderr)
        return 3

    rendered = canonical_json(plan) + "\n"
    if args.plan_output:
        try:
            Path(args.plan_output).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"wsm-install: cannot write plan: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
