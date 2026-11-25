# SPDX-License-Identifier: LicenseRef-Volnist
"""x86-64 micro-architecture level evidence, derived from /proc/cpuinfo only.

This is a separate, versioned contract on top of the hardware report (issue
#148). It does not change report schema 1.0.0 and does not run any external
command: the collector's promise that it reads sysfs and procfs only still
holds.

Why levels and not vendor strings: the x86-64 psABI defines named levels
(v2, v3, v4) as cumulative sets of CPU features. A chip with AVX but no AVX2
is v2, not "almost v3". Deciding by vendor or model name would be guessing.

What this module deliberately does not do:

- it does not enable anything. A level is evidence, not a build flag;
- it does not claim a performance win. The measured gain from v2 to v3 is a few
  percent for most workloads and larger only for compression, cryptography and
  numeric code - and those libraries already dispatch at runtime;
- it does not read /proc/cpuinfo flags as "the CPU can do this". The kernel
  clears AVX-family flags when OS support (XSAVE/OSXSAVE) is absent, so a
  missing flag means "not usable now", not "not present in silicon".
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
VERSION = "0.1.0"

# Cumulative feature sets from the x86-64 psABI. Each level includes every
# feature of the levels below it; /proc/cpuinfo spellings are used (pni = SSE3,
# abm = LZCNT on both Intel and AMD under Linux).
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


def read_cpuinfo_flags(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return the flag set of the first processor block plus a few raw fields."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise IsaError("cpuinfo.unreadable", f"cannot read {path}: {exc}") from exc

    flags: list[str] = []
    fields: dict[str, str] = {}
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            if key == "flags":
                flags = sorted(set(value.split()))
            elif key in {"vendor_id", "model name", "cpu family"} and key not in fields:
                fields[key] = value
        break  # first processor block only: levels are uniform across sockets
    return flags, fields


def evaluate(flags: list[str], architecture: str) -> dict[str, Any]:
    """Compute level support from a flag list. Pure: no I/O, easy to test."""
    if architecture.lower() not in X86_ARCHITECTURES:
        raise IsaError(
            "isa.not-x86",
            f"x86-64 levels are defined only for x86-64, got {architecture!r}; "
            "this evidence does not apply to other architectures",
        )

    present = set(flags)
    result: dict[str, Any] = {}
    # Cumulative: a level counts as supported only if every lower level is too.
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
            "osxsave is absent: AVX-family state is not managed by the OS, so "
            "AVX levels are not usable even if the silicon has them"
        )
    if fields.get("vendor_id") and "GenuineIntel" not in fields["vendor_id"] and "AuthenticAMD" not in fields["vendor_id"]:
        warnings.append(
            f"unexpected vendor_id {fields['vendor_id']!r}; levels are computed "
            "from features, not from the vendor, but this is worth noting"
        )

    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "architecture": architecture,
        "vendor": fields.get("vendor_id", "unknown"),
        "model_name": fields.get("model name", "unknown"),
        "level_semantics": "cumulative x86-64 psABI micro-architecture levels",
        "levels": levels,
        "evidence": {
            "source": source,
            "kind": "live-observation",
            "confidence": "confirmed",
            "feature_count": len(flags),
        },
        "warnings": warnings,
        "limits": [
            "a supported level is evidence about the running CPU and kernel, not a build decision",
            "no performance claim is made: v2-to-v3 gains are workload-dependent",
            "the kernel clears AVX-family flags when OS support is missing, so absence means 'not usable now'",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsm-cpu-isa",
        description=(
            "Report x86-64 micro-architecture levels from /proc/cpuinfo. "
            "Read-only: no external commands, no network, no writes outside stdout."
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
    flags, fields = read_cpuinfo_flags(Path(args.cpuinfo))

    try:
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
