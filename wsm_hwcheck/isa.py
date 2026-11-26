# SPDX-License-Identifier: LicenseRef-Volnist
"""x86-64 micro-architecture level evidence from kernel-exposed CPU flags.

This is a separate, versioned contract on top of the hardware report (issue
#148). It does not change report schema 1.0.0 and does not run external
commands: the collector's promise that it reads sysfs and procfs only still
holds.

The feature set is the intersection of every processor block reported by
/proc/cpuinfo. This is deliberately conservative: a process may migrate
between logical CPUs, so a system-wide dispatch level must be usable on all
reported processors. Missing flags are an unavailable evidence source, not
proof that the silicon lacks a feature.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform as host_platform
import sys
from pathlib import Path
from typing import Any

SCHEMA = "wsm-cpu-isa/1"
VERSION = "0.1.2"

# Cumulative feature sets from the x86-64 psABI. Each level includes every
# feature of the levels below it; /proc/cpuinfo spellings are used (pni = SSE3,
# abm = LZCNT on Linux x86).
LEVELS: dict[str, tuple[str, ...]] = {
    "x86-64-v2": (
        "cx16",
        "lahf_lm",
        "popcnt",
        "pni",
        "ssse3",
        "sse4_1",
        "sse4_2",
    ),
    "x86-64-v3": (
        "avx",
        "avx2",
        "bmi1",
        "bmi2",
        "f16c",
        "fma",
        "abm",
        "movbe",
        "osxsave",
    ),
    "x86-64-v4": (
        "avx512f",
        "avx512bw",
        "avx512cd",
        "avx512dq",
        "avx512vl",
    ),
}

X86_ARCHITECTURES = {"x86_64", "amd64", "x86-64"}


class IsaError(Exception):
    """Refusal with a stable code, mirroring the rest of the tooling."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _parse_block(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key and key not in fields:
            fields[key] = value
    return fields


def read_cpuinfo_flags(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return the common flags across all processor blocks.

    A missing or empty flags field in any processor block makes a machine-wide
    claim unsafe. The caller receives a stable refusal instead of a partial
    intersection that could overstate what is usable after CPU migration.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise IsaError("cpuinfo.unreadable", f"cannot read {path}: {exc}") from exc

    blocks = [block for block in text.split("\n\n") if block.strip()]
    if not blocks:
        raise IsaError("cpuinfo.empty", f"{path} contains no processor information")

    parsed_blocks = [_parse_block(block) for block in blocks]
    processor_blocks = [
        fields for fields in parsed_blocks if "processor" in fields
    ]

    # A malformed non-empty block must not disappear from a system-wide
    # intersection. Keep the one-block fallback only for alternate/synthetic
    # procfs fixtures that have no processor keys at all.
    if processor_blocks and len(processor_blocks) != len(parsed_blocks):
        malformed = len(parsed_blocks) - len(processor_blocks)
        raise IsaError(
            "cpuinfo.processor-block-incomplete",
            f"{malformed} non-empty block(s) in {path} do not identify a processor; "
            "refusing to compute a system-wide ISA verdict from partial input",
        )
    if not processor_blocks:
        if len(parsed_blocks) != 1:
            raise IsaError(
                "cpuinfo.processor-block-incomplete",
                f"{path} contains multiple non-empty blocks but no processor identifiers",
            )
        processor_blocks = parsed_blocks
    flag_sets: list[set[str]] = []
    missing_flags = 0
    for fields in processor_blocks:
        raw_flags = fields.get("flags")
        if not raw_flags:
            missing_flags += 1
        else:
            flag_sets.append(set(raw_flags.split()))

    if not flag_sets:
        raise IsaError(
            "cpuinfo.flags-unavailable",
            f"no processor block in {path} exposes a non-empty flags field",
        )
    if missing_flags:
        raise IsaError(
            "cpuinfo.flags-incomplete",
            f"{missing_flags} of {len(processor_blocks)} processor blocks in {path} "
            "do not expose a non-empty flags field; refusing a system-wide ISA verdict",
        )

    # Runtime dispatch must remain safe regardless of which logical CPU runs
    # the process. Do not infer uniformity from only the first processor.
    common_flags = set.intersection(*flag_sets)

    result_fields: dict[str, str] = {}
    for key in ("vendor_id", "model name", "cpu family"):
        value = processor_blocks[0].get(key)
        if value:
            result_fields[key] = value
    result_fields["logical_processor_count"] = str(len(processor_blocks))
    return sorted(common_flags), result_fields


def evaluate(flags: list[str], architecture: str) -> dict[str, Any]:
    """Compute cumulative level evidence from kernel-exposed flags."""
    if architecture.lower() not in X86_ARCHITECTURES:
        raise IsaError(
            "isa.not-x86",
            f"x86-64 levels are defined only for x86-64, got {architecture!r}; "
            "this evidence does not apply to other architectures",
        )

    present = set(flags)
    result: dict[str, Any] = {}
    cumulative_ok = True
    for level in ("x86-64-v2", "x86-64-v3", "x86-64-v4"):
        missing = [feature for feature in LEVELS[level] if feature not in present]
        supported = cumulative_ok and not missing
        cumulative_ok = supported
        result[level] = {
            "supported": supported,
            "missing": missing,
        }

    highest = "x86-64-v1"
    for level in ("x86-64-v2", "x86-64-v3", "x86-64-v4"):
        if result[level]["supported"]:
            highest = level
    result["highest_supported"] = highest
    return result


def build_evidence(
    flags: list[str],
    fields: dict[str, str],
    architecture: str,
    source: str,
) -> dict[str, Any]:
    levels = evaluate(flags, architecture)
    warnings: list[str] = []
    if "osxsave" not in set(flags):
        warnings.append(
            "osxsave is not exposed in the common kernel flags; an AVX-family "
            "level is not confirmed by this evidence"
        )
    if fields.get("vendor_id") and fields["vendor_id"] not in {
        "GenuineIntel",
        "AuthenticAMD",
    }:
        warnings.append(
            f"unexpected vendor_id {fields['vendor_id']!r}; levels are computed "
            "from exposed features, not from the vendor"
        )

    processor_count = int(fields.get("logical_processor_count", "1"))
    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "architecture": architecture,
        "vendor": fields.get("vendor_id", "unknown"),
        "model_name": fields.get("model name", "unknown"),
        "level_semantics": (
            "cumulative x86-64 psABI levels from the intersection of kernel-exposed "
            "flags across all processor blocks reported by procfs"
        ),
        "levels": levels,
        "evidence": {
            "source": source,
            "kind": "live-observation",
            "confidence": "confirmed",
            "scope": "common-kernel-exposed-flags",
            "logical_processor_count": processor_count,
            "feature_count": len(flags),
        },
        "warnings": warnings,
        "limits": [
            "a supported level is evidence about flags exposed by the running kernel, not a silicon inventory or build decision",
            "the /proc/cpuinfo flag list is incomplete; an absent flag does not prove the hardware lacks that feature",
            "the intersection is a conservative set common to all reported logical processors",
            "no performance claim is made: v2-to-v3 gains are workload-dependent",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-cpu-isa",
        description=(
            "Report common x86-64 micro-architecture levels from all "
            "/proc/cpuinfo processor blocks. Read-only; no external commands."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    parser.add_argument("--cpuinfo", default="/proc/cpuinfo", help=argparse.SUPPRESS)
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="optional hardware report to cross-check architecture and vendor",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    architecture = host_platform.machine()
    try:
        # Reject non-x86 before attempting to parse architecture-specific procfs
        # fields; ARM/RISC-V must not fail with a misleading missing-flags error.
        evaluate([], architecture)
        flags, fields = read_cpuinfo_flags(Path(args.cpuinfo))
        evidence = build_evidence(flags, fields, architecture, f"procfs:{args.cpuinfo}")
    except IsaError as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")

    if args.report:
        try:
            report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.exit(2, f"{parser.prog}: cannot read report: {exc}\n")
        report_arch = report.get("environment", {}).get("architecture")
        if report_arch and report_arch != architecture:
            evidence["warnings"].append(
                f"report architecture {report_arch!r} differs from the running "
                f"machine {architecture!r}; the report describes another host"
            )
        evidence["cross_check"] = {
            "report_id": report.get("report_id"),
            "report_architecture": report_arch,
            "report_schema_version": report.get("schema_version"),
        }

    sys.stdout.write(
        json.dumps(
            evidence,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
