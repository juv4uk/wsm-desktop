# SPDX-License-Identifier: GPL-3.0-or-later
"""Run wsm-hwcheck inside a bounded, device-isolated QEMU TCG guest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.qemu_boot_smoke import (
    MAX_SERIAL_CAPTURE_BYTES,
    MAX_STDERR_CAPTURE_BYTES,
    run_bounded_process,
)

REPORT_BEGIN = b"WSM_HWCHECK_REPORT_BEGIN"
REPORT_END = b"WSM_HWCHECK_REPORT_END"
GUEST_DONE = "WSM_HWCHECK_GUEST_DONE"


def build_qemu_command(qemu: str, kernel: Path, initramfs: Path) -> list[str]:
    """Boot a kernel + initramfs with TCG only, no disk, NIC, or host passthrough."""
    return [
        qemu,
        "-nodefconfig",
        "-no-user-config",
        "-nodefaults",
        "-machine", "q35,accel=tcg",
        "-cpu", "max",
        "-m", "1024",
        "-smp", "2",
        "-kernel", str(kernel),
        "-initrd", str(initramfs),
        "-append", "console=ttyS0,115200 rdinit=/init panic=-1 loglevel=4",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-nic", "none",
        "-no-reboot",
    ]


def extract_hardware_report(serial_output: bytes) -> bytes:
    """Extract exactly one guest report between explicit serial markers."""
    if serial_output.count(REPORT_BEGIN) != 1 or serial_output.count(REPORT_END) != 1:
        raise ValueError("guest serial stream must contain exactly one report boundary pair")

    begin_at = serial_output.find(REPORT_BEGIN)
    payload_start = begin_at + len(REPORT_BEGIN)
    while payload_start < len(serial_output) and serial_output[payload_start:payload_start + 1] in (b"\r", b"\n"):
        payload_start += 1

    end_at = serial_output.find(REPORT_END, payload_start)
    if end_at < 0:
        raise ValueError("guest report end marker is missing or out of order")

    payload = serial_output[payload_start:end_at].strip(b"\r\n")
    if not payload:
        raise ValueError("guest hardware report is empty")
    return payload


def validate_hardware_report(report: Any, schema: dict[str, Any]) -> int:
    """Validate schema and the read-only, privacy, and inventory-only invariants."""
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(report),
        key=lambda error: (list(map(str, error.absolute_path)), error.message),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise ValueError(f"hardware report schema violation at {location}: {first.message}")

    if report.get("schema_version") != "1.0.0":
        raise ValueError("guest report did not use hardware report schema v1.0.0")

    privacy = report.get("privacy", {})
    for field in (
        "network_requests_performed",
        "network_upload_performed",
        "sensitive_identifiers_included",
    ):
        if privacy.get(field) is not False:
            raise ValueError(f"guest report does not affirm {field}=false")

    devices = report.get("devices", [])
    functional_test_count = 0
    for index, device in enumerate(devices):
        functional_tests = device.get("functional_tests", [])
        if not isinstance(functional_tests, list):
            raise ValueError(f"devices/{index}/functional_tests is not an array")
        for test_index, test in enumerate(functional_tests):
            functional_test_count += 1
            status = test.get("status")
            if status not in {"unknown", "not-tested"}:
                raise ValueError(
                    f"devices/{index}/functional_tests/{test_index} claims an unexecuted status {status!r}"
                )
    if functional_test_count:
        raise ValueError("inventory-only guest unexpectedly emitted functional test records")

    collectors = report.get("collectors", [])
    if not any(
        item.get("name") == "wsm-hwcheck-sysfs" and item.get("available") is True
        for item in collectors
    ):
        raise ValueError("report does not contain the actual wsm-hwcheck sysfs collector")
    return len(devices)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--initramfs", required=True, type=Path)
    parser.add_argument("--schema", type=Path, default=Path("schemas/hardware-report.schema.json"))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)

    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        parser.error("qemu-system-x86_64 is required")
    if not args.kernel.is_file() or not args.initramfs.is_file() or not args.schema.is_file():
        parser.error("kernel, initramfs, and schema must be regular files")
    if not 1 <= args.timeout_seconds <= 180:
        parser.error("--timeout-seconds must be between 1 and 180")

    command = build_qemu_command(qemu, args.kernel.resolve(), args.initramfs.resolve())
    forbidden = {"-drive", "-blockdev", "-device", "-netdev", "-fsdev", "-virtfs", "-pflash", "-bios"}
    if any(argument in forbidden for argument in command):
        parser.error("QEMU command contains a forbidden disk, network, passthrough, or firmware argument")
    if command[command.index("-machine") + 1] != "q35,accel=tcg":
        parser.error("QEMU must use TCG software emulation")
    if command[command.index("-nic") + 1] != "none":
        parser.error("QEMU network devices must be disabled")

    result = run_bounded_process(
        command,
        timeout_seconds=args.timeout_seconds,
        marker=GUEST_DONE,
        max_stdout_bytes=MAX_SERIAL_CAPTURE_BYTES,
        max_stderr_bytes=MAX_STDERR_CAPTURE_BYTES,
    )
    if result.timed_out:
        raise RuntimeError("QEMU guest exceeded its wall-clock timeout")
    if result.returncode != 0:
        raise RuntimeError(f"QEMU exited with status {result.returncode}")
    if not result.marker_seen:
        raise RuntimeError("guest completion marker was not observed")
    if result.stdout_truncated or result.stderr_truncated:
        raise RuntimeError("guest serial or QEMU stderr exceeded the bounded capture limit")

    report_bytes = extract_hardware_report(result.stdout_tail)
    report = json.loads(report_bytes)
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    device_count = validate_hardware_report(report, schema)

    categories = Counter(device.get("category", "unknown") for device in report.get("devices", []))
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    print("PASS: actual wsm-hwcheck CLI executed inside an isolated QEMU TCG guest.")
    print(f"schema_version={report['schema_version']} devices={device_count} collectors={len(report['collectors'])}")
    print(f"device_categories={json.dumps(dict(sorted(categories.items())), sort_keys=True)}")
    print("network_requests_performed=false network_upload_performed=false")
    print("functional_tests=0 host_disk_devices=0 host_network_devices=0 host_passthrough=0")
    print(f"report_bytes={len(report_bytes)} report_sha256={report_sha256}")
    print(
        "qemu_returncode=0 "
        f"serial_bytes_seen={result.stdout_bytes_seen} "
        f"stderr_bytes_seen={result.stderr_bytes_seen} "
        f"serial_truncated={str(result.stdout_truncated).lower()} "
        f"stderr_truncated={str(result.stderr_truncated).lower()}"
    )
    print("Scope: QEMU guest runtime validation only; not physical hardware certification or a WSM installer ISO.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"wsm-hwcheck-qemu-guest: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
