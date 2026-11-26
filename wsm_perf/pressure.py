# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only system pressure telemetry for explicit WSM benchmark runs.

All observations are system-wide. This module never writes procfs or sysfs.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


PSI_RESOURCES = ("cpu", "memory", "io")
PSI_KEYS = ("avg10", "avg60", "avg300", "total")
ZRAM_STAT_FIELDS = {
    "mm_stat": (
        "orig_data_size",
        "compr_data_size",
        "mem_used_total",
        "mem_limit",
        "mem_used_max",
        "same_pages",
        "pages_compacted",
        "huge_pages",
        "huge_pages_since",
    ),
    "io_stat": ("failed_reads", "failed_writes", "invalid_io", "notify_free"),
    "bd_stat": ("bd_count", "bd_reads", "bd_writes"),
}
ZRAM_MIN_FIELDS = {"mm_stat": 8, "io_stat": 4, "bd_stat": 3}
ZRAM_DEVICE_NAME = re.compile(r"zram[0-9]+\Z")


def parse_psi(text: str) -> dict[str, dict[str, int | float]]:
    """Розібрати PSI без припущень про наявність рядка full."""
    result: dict[str, dict[str, int | float]] = {}
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        kind = tokens[0]
        if kind not in ("some", "full") or kind in result:
            raise ValueError("invalid or duplicate PSI line")
        fields: dict[str, int | float] = {}
        for token in tokens[1:]:
            key, separator, value = token.partition("=")
            if not separator or key not in PSI_KEYS or key in fields:
                raise ValueError("invalid PSI field")
            if key == "total":
                if not value.isdecimal():
                    raise ValueError("invalid PSI total")
                fields[key] = int(value)
            else:
                try:
                    number = float(value)
                except ValueError as exc:
                    raise ValueError("invalid PSI average") from exc
                if not math.isfinite(number) or not 0.0 <= number <= 100.0:
                    raise ValueError("PSI average outside 0..100")
                fields[key] = number
        if set(fields) != set(PSI_KEYS):
            raise ValueError("incomplete PSI line")
        result[kind] = fields
    if not result:
        raise ValueError("empty PSI report")
    return result


def _read_text_status(path: Path) -> dict[str, str]:
    """Read only one procfs/sysfs attribute and retain failure as evidence."""
    try:
        return {"status": "available", "text": path.read_text(encoding="utf-8").strip()}
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "not-found"}
    except PermissionError:
        return {"status": "unavailable", "reason": "permission-denied"}
    except OSError:
        return {"status": "unavailable", "reason": "read-error"}
    except UnicodeError:
        return {"status": "unavailable", "reason": "invalid-encoding"}


def read_psi_snapshot(root: Path = Path("/proc/pressure")) -> dict[str, Any]:
    """Collect system-wide PSI counters. This function never writes procfs."""
    snapshot: dict[str, Any] = {}
    for resource in PSI_RESOURCES:
        path = root / resource
        raw = _read_text_status(path)
        if raw["status"] != "available":
            snapshot[resource] = {
                "status": "unavailable",
                "source": f"/proc/pressure/{resource}",
                "reason": raw["reason"],
            }
            continue
        try:
            lines = parse_psi(raw["text"])
        except ValueError:
            snapshot[resource] = {
                "status": "unavailable",
                "source": f"/proc/pressure/{resource}",
                "reason": "invalid-format",
            }
            continue
        snapshot[resource] = {
            "status": "available",
            "source": f"/proc/pressure/{resource}",
            "lines": lines,
        }
    return snapshot


def parse_zram_stat(text: str, stat_name: str) -> dict[str, Any]:
    """Parse named zram counters; preserve newer trailing fields verbatim."""
    if stat_name not in ZRAM_STAT_FIELDS:
        raise ValueError(f"unsupported zram statistic: {stat_name}")
    tokens = text.split()
    if len(tokens) < ZRAM_MIN_FIELDS[stat_name]:
        raise ValueError(f"incomplete {stat_name}")
    try:
        values = [int(token, 10) for token in tokens]
    except ValueError as exc:
        raise ValueError(f"non-integer {stat_name}") from exc
    if any(value < 0 for value in values):
        raise ValueError(f"negative {stat_name}")
    names = ZRAM_STAT_FIELDS[stat_name]
    fields = dict(zip(names, values[: len(names)]))
    result: dict[str, Any] = {
        "status": "available" if len(values) >= len(names) else "partial",
        "fields": fields,
        "raw_values": values,
    }
    if len(values) < len(names):
        result["missing_fields"] = list(names[len(values) :])
    if len(values) > len(names):
        result["extra_values"] = values[len(names) :]
    return result


def read_zram_snapshot(root: Path = Path("/sys/block")) -> dict[str, Any]:
    """Collect zram stats/config through read-only sysfs attributes."""
    devices: dict[str, Any] = {}
    try:
        candidates = sorted(
            path for path in root.glob("zram*")
            if ZRAM_DEVICE_NAME.fullmatch(path.name) and path.is_dir()
        )
    except OSError:
        return {"status": "unavailable", "reason": "sysfs-read-error", "devices": {}}

    for device in candidates:
        stats: dict[str, Any] = {}
        for stat_name in ZRAM_STAT_FIELDS:
            raw = _read_text_status(device / stat_name)
            if raw["status"] != "available":
                stats[stat_name] = raw
                continue
            try:
                stats[stat_name] = parse_zram_stat(raw["text"], stat_name)
            except ValueError:
                stats[stat_name] = {"status": "unavailable", "reason": "invalid-format"}

        algorithm = _read_text_status(device / "comp_algorithm")
        backing = _read_text_status(device / "backing_dev")
        algorithm_text = algorithm.get("text", "")
        active_match = re.search(r"\\[([A-Za-z0-9_-]+)\\]", algorithm_text)
        backing_device = backing.get("text", "unknown")
        config_status = (
            "available"
            if algorithm.get("status") == "available"
            and active_match is not None
            and backing.get("status") == "available"
            and bool(backing_device)
            else "partial"
        )
        config = {
            "status": config_status,
            "active_compressor": active_match.group(1) if active_match else "unknown",
            "compressor_report": algorithm_text or "unknown",
            "backing_device": backing_device,
            "sources": {
                "comp_algorithm": {
                    "status": algorithm.get("status", "unknown"),
                    "reason": algorithm.get("reason"),
                },
                "backing_dev": {
                    "status": backing.get("status", "unknown"),
                    "reason": backing.get("reason"),
                },
            },
        }
        devices[device.name] = {
            "status": "available" if (
                config_status == "available"
                and all(value.get("status") == "available" for value in stats.values())
            ) else "partial",
            "config": config,
            "stats": stats,
        }

    if not devices:
        return {"status": "unavailable", "reason": "no-zram-devices", "devices": {}}
    return {
        "status": "available" if all(
            device.get("status") == "available" for device in devices.values()
        ) else "partial",
        "devices": devices,
    }


def read_pressure_snapshot(
    proc_pressure_root: Path = Path("/proc/pressure"),
    sys_block_root: Path = Path("/sys/block"),
) -> dict[str, Any]:
    """Capture read-only system-wide pressure immediately outside timed samples."""
    return {
        "psi": read_psi_snapshot(proc_pressure_root),
        "zram": read_zram_snapshot(sys_block_root),
    }


def _counter_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("status") not in ("available", "partial") or after.get("status") not in ("available", "partial"):
        return {"status": "unknown", "reason": "counter-unavailable", "fields": {}}
    left = before.get("fields", {})
    right = after.get("fields", {})
    input_partial = before.get("status") != "available" or after.get("status") != "available"
    missing_before = sorted(set(right) - set(left))
    missing_after = sorted(set(left) - set(right))
    field_set_changed = bool(missing_before or missing_after)
    deltas: dict[str, int | None] = {}
    for key in sorted(set(left) & set(right)):
        start_value, end_value = left[key], right[key]
        deltas[key] = end_value - start_value if end_value >= start_value else None
    if not deltas:
        return {"status": "unknown", "reason": "counter-fields-unavailable", "fields": {}}
    reset_detected = any(value is None for value in deltas.values())
    return {
        "status": (
            "available"
            if not input_partial and not field_set_changed and not reset_detected
            else "partial"
        ),
        "reason": (
            "counter-reset" if reset_detected else
            "field-set-changed" if field_set_changed else
            "partial-source" if input_partial else None
        ),
        "fields": deltas,
        "missing_before_fields": missing_before,
        "missing_after_fields": missing_after,
    }

def compare_pressure_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Summarize counter deltas; values are system-wide, not process attribution."""
    psi_result: dict[str, Any] = {}
    before_psi, after_psi = before.get("psi", {}), after.get("psi", {})
    for resource in PSI_RESOURCES:
        left = before_psi.get(resource, {"status": "unavailable"})
        right = after_psi.get(resource, {"status": "unavailable"})
        if left.get("status") != "available" or right.get("status") != "available":
            psi_result[resource] = {
                "status": "unknown",
                "before": left,
                "after": right,
                "total_delta_us": {},
            }
            continue
        totals: dict[str, int | None] = {}
        left_lines, right_lines = left.get("lines", {}), right.get("lines", {})
        line_sets_match = set(left_lines) == set(right_lines)
        for kind in sorted(set(left_lines) & set(right_lines)):
            start = left_lines[kind].get("total")
            end = right_lines[kind].get("total")
            totals[kind] = end - start if isinstance(start, int) and isinstance(end, int) and end >= start else None
        psi_result[resource] = {
            "status": (
                "available"
                if line_sets_match and totals and all(v is not None for v in totals.values())
                else "partial"
            ),
            "before": left,
            "after": right,
            "total_delta_us": totals,
        }

    zram_result: dict[str, Any] = {}
    before_zram = before.get("zram", {}).get("devices", {})
    after_zram = after.get("zram", {}).get("devices", {})
    for name in sorted(set(before_zram) | set(after_zram)):
        left, right = before_zram.get(name), after_zram.get(name)
        if left is None or right is None:
            zram_result[name] = {
                "status": "unknown",
                "reason": "device-set-changed",
                "before": left,
                "after": right,
                "counter_delta": {},
            }
            continue
        left_stats, right_stats = left.get("stats", {}), right.get("stats", {})
        deltas = {}
        for stat_name in ("io_stat", "bd_stat"):
            deltas[stat_name] = _counter_deltas(
                left_stats.get(stat_name, {}),
                right_stats.get(stat_name, {}),
            )
        mm_before = left_stats.get("mm_stat", {"status": "unknown"})
        mm_after = right_stats.get("mm_stat", {"status": "unknown"})
        config_before = left.get("config", {"status": "unknown"})
        config_after = right.get("config", {"status": "unknown"})
        config_values_match = (
            config_before.get("active_compressor") == config_after.get("active_compressor")
            and config_before.get("backing_device") == config_after.get("backing_device")
        )
        config_stable = (
            config_before.get("status") == "available"
            and config_after.get("status") == "available"
            and config_values_match
        )
        complete = (
            left.get("status") == "available"
            and right.get("status") == "available"
            and config_stable
            and all(delta.get("status") == "available" for delta in deltas.values())
            and mm_before.get("status") == "available"
            and mm_after.get("status") == "available"
        )
        zram_result[name] = {
            "status": "available" if complete else "partial",
            "before": left,
            "after": right,
            "config": {
                "status": "available" if config_stable else "partial",
                "changed": not config_values_match,
                "before": config_before,
                "after": config_after,
            },
            # mm_stat mixes byte-valued sizes with page fields; preserve raw snapshots.
            "mm_stat": {"before": mm_before, "after": mm_after},
            "counter_delta": deltas,
        }

    return {
        "scope": "system-wide",
        "interpretation": (
            "PSI and zram include unrelated system activity; deltas describe the "
            "workload interval but do not attribute pressure to this process"
        ),
        "psi": psi_result,
        "zram": {
            "status": (
                "unavailable" if not zram_result else
                "available" if all(item["status"] == "available" for item in zram_result.values()) else
                "partial"
            ),
            "devices": zram_result,
        },
    }
