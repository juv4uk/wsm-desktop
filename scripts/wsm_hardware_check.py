#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-command, read-only hardware preview check for a WSM release tree.

The script collects a local hardware report and asks the diagnostic-only
installer prototype to draft plans for both backend aliases.  It never opens
block devices, invokes a backend, changes firmware/bootloader state, or uses
the network.  The only writes are regular files inside the explicit output
directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wsm_install.plan import canonical_json  # noqa: E402  (path set above)

RELEASE_INFO = ROOT / "RELEASE-INFO.json"
SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"
BACKENDS = ("guix", "nix")

SAFE_EXECUTION = {
    "dry_run": True,
    "plan_confirmable": False,
    "mutations_authorized": False,
    "backend_invoked": False,
    "disk_access_performed": False,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_release_info() -> dict[str, Any]:
    try:
        value = json.loads(RELEASE_INFO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"wsm-hardware-check: cannot read {RELEASE_INFO}: {exc}")
    if not isinstance(value, dict) or "version" not in value:
        raise SystemExit(f"wsm-hardware-check: invalid {RELEASE_INFO}")
    return value


def source_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def prepare_output(raw: str) -> Path:
    requested = Path(raw).expanduser()
    try:
        output = requested.resolve(strict=False)
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot resolve output path: {exc}")

    for special in (Path("/dev"), Path("/proc"), Path("/sys")):
        if output == special or special in output.parents:
            raise SystemExit(f"wsm-hardware-check: output must not be under {special}")

    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise SystemExit("wsm-hardware-check: output must be a real directory, not a symlink")
        if any(output.iterdir()):
            raise SystemExit("wsm-hardware-check: output directory must be empty")
    else:
        try:
            parent = output.parent.resolve(strict=True)
        except OSError as exc:
            raise SystemExit(f"wsm-hardware-check: output parent is unavailable: {exc}")
        if not parent.is_dir():
            raise SystemExit("wsm-hardware-check: output parent is not a directory")
        try:
            output.mkdir(mode=0o700)
        except OSError as exc:
            raise SystemExit(f"wsm-hardware-check: cannot create output directory: {exc}")

    try:
        os.chmod(output, 0o700)
    except OSError:
        pass
    return output


def run_module(module: str, args: list[str], output: Path, label: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    command = [sys.executable, "-m", module, *args]

    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot start {module}: {exc}")

    (output / f"{label}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")
    return {
        "command": " ".join([Path(sys.executable).name, "-m", module, *args]),
        "exit_code": result.returncode,
        "stdout_log": f"{label}.stdout.log",
        "stderr_log": f"{label}.stderr.log",
    }


def verify_plan(plan: dict[str, Any], report_bytes: bytes) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    execution = plan.get("execution")
    if not isinstance(execution, dict):
        errors.append("plan has no execution object")
    else:
        for key, expected in SAFE_EXECUTION.items():
            if execution.get(key) is not expected:
                errors.append(f"execution.{key}={execution.get(key)!r}, expected {expected!r}")

    if plan.get("plan_status") != "diagnostic-only":
        errors.append(f"plan_status={plan.get('plan_status')!r}, expected 'diagnostic-only'")
    if plan.get("plan_mode") != "dry-run":
        errors.append(f"plan_mode={plan.get('plan_mode')!r}, expected 'dry-run'")

    source = plan.get("source_report")
    expected_report_digest = sha256_bytes(report_bytes)
    if not isinstance(source, dict) or source.get("sha256") != expected_report_digest:
        errors.append("source_report.sha256 does not match the exact report bytes")

    unsigned = dict(plan)
    stated_digest = unsigned.pop("plan_sha256", None)
    calculated = sha256_bytes(canonical_json(unsigned).encode("utf-8"))
    if stated_digest != calculated:
        errors.append("plan_sha256 does not match canonical plan bytes")

    execution_errors = [item for item in errors if item.startswith("execution.")]
    return (
        {
            "plan_status": plan.get("plan_status"),
            "backend_id": plan.get("backend", {}).get("id") if isinstance(plan.get("backend"), dict) else None,
            "source_report_sha256_matches": (
                isinstance(source, dict) and source.get("sha256") == expected_report_digest
            ),
            "plan_sha256_matches": stated_digest == calculated,
            "safe_execution_flags": not execution_errors,
        },
        errors,
    )


def write_sums(output: Path) -> Path:
    destination = output / "SHA256SUMS"
    lines = []
    for path in sorted(output.iterdir()):
        if path.name == destination.name or not path.is_file():
            continue
        lines.append(f"{sha256_file(path)}  {path.name}\n")
    destination.write_text("".join(lines), encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wsm-hardware-check",
        description="Collect a read-only WSM hardware report and verify diagnostic-only draft plans.",
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="DIR",
        help="empty output directory for report, plans, logs and manifest",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="use an existing report instead of collecting from /sys and /proc (for QA only)",
    )
    args = parser.parse_args(argv)

    release = load_release_info()
    if not SCHEMA.is_file():
        raise SystemExit(f"wsm-hardware-check: missing schema {SCHEMA}")
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        raise SystemExit(
            "wsm-hardware-check: jsonschema 4.26.0 is required; "
            "install requirements-install.txt first"
        )

    output = prepare_output(args.out)
    commands: list[dict[str, Any]] = []
    errors: list[str] = []

    if args.report:
        source = Path(args.report).expanduser().resolve(strict=True)
        report_bytes = source.read_bytes()
        report_destination = output / "report.json"
        report_destination.write_bytes(report_bytes)
        commands.append(
            {
                "command": f"copy existing report {source.name}",
                "exit_code": 0,
                "stdout_log": None,
                "stderr_log": None,
            }
        )
    else:
        commands.append(
            run_module("wsm_hwcheck", ["--output", str(output / "report.json")], output, "hwcheck")
        )
        try:
            report_bytes = (output / "report.json").read_bytes()
        except OSError as exc:
            raise SystemExit(f"wsm-hardware-check: collector did not write a report: {exc}")

    report_verification = {
        "raw_sha256": sha256_bytes(report_bytes),
        "bytes": len(report_bytes),
    }

    plans: dict[str, Any] = {}
    for backend in BACKENDS:
        plan_name = f"plan-{backend}.json"
        entry = run_module(
            "wsm_install",
            [
                "--preflight",
                "--report",
                str(output / "report.json"),
                "--backend",
                backend,
                "--dry-run",
                "--plan-output",
                str(output / plan_name),
                "--quiet",
            ],
            output,
            f"install-{backend}",
        )
        commands.append(entry)
        plan_path = output / plan_name
        if entry["exit_code"] == 3 and not plan_path.exists():
            plans[backend] = {
                "status": "safely-blocked",
                "reason_log": entry["stderr_log"],
                "verification_errors": [],
            }
            continue
        if entry["exit_code"] != 0 or not plan_path.exists():
            errors.append(f"{backend}: no safe plan emitted (exit={entry['exit_code']})")
            plans[backend] = {
                "status": "failed",
                "reason_log": entry["stderr_log"],
                "verification_errors": [f"exit={entry['exit_code']}"],
            }
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{backend}: emitted plan is not valid JSON: {exc}")
            plans[backend] = {"status": "failed", "verification_errors": [str(exc)]}
            continue
        details, plan_errors = verify_plan(plan, report_bytes)
        details["status"] = "verified-diagnostic" if not plan_errors else "failed"
        details["verification_errors"] = plan_errors
        plans[backend] = details
        errors.extend(f"{backend}: {message}" for message in plan_errors)

    if any(item["status"] == "safely-blocked" for item in plans.values()) and not errors:
        overall = "preflight-blocked"
    elif errors:
        overall = "failed"
    else:
        overall = "pass"

    manifest = {
        "schema": "wsm-hardware-check-manifest/1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release": {
            "id": release.get("release_id"),
            "version": release.get("version"),
            "source_commit": source_commit(),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "report": report_verification,
        "plans": plans,
        "commands": commands,
        "safety": {
            "network_used": False,
            "root_required": False,
            "block_device_access": False,
            "bootloader_or_firmware_changes": False,
            "backend_invoked": False,
        },
        "overall": overall,
        "errors": errors,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_sums(output)

    print(f"WSM {release.get('version')}: {overall}")
    for backend in BACKENDS:
        print(f"  {backend}: {plans[backend]['status']}")
    print(f"  output: {output}")
    return 0 if overall in {"pass", "preflight-blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
