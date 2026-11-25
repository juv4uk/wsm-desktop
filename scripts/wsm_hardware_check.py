#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-command, read-only hardware preview check for a WSM release tree.

The script collects a local hardware report and asks the diagnostic-only
installer prototype to draft plans for both backend aliases.  It never opens
block devices, invokes a backend, changes firmware/bootloader state, or uses
the network.  The only writes are regular files inside the explicit output
directory.  Logged commands use argv arrays and path placeholders; no absolute
user path is written into the manifest or logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELEASE_INFO = ROOT / "RELEASE-INFO.json"
SCHEMA = ROOT / "schemas" / "hardware-report.schema.json"
BACKENDS = ("guix", "nix")
EXPECTED_BACKEND_IDS = {"guix": "guix-system", "nix": "nixos"}
BLOCKED_MARKER = "wsm-install: no plan emitted because required critical evidence is unresolved"
MAX_REPORT_BYTES = 8 * 1024 * 1024

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


def canonical_json(value: Any) -> str:
    """Independent canonical serialization, matching the handoff contract.

    Deliberately not imported from the producer of the plan: a bug in the
    producer's hashing must be detectable here.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_release_info() -> dict[str, Any]:
    try:
        value = json.loads(RELEASE_INFO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"wsm-hardware-check: cannot read {RELEASE_INFO}: {exc}")
    if not isinstance(value, dict) or "version" not in value:
        raise SystemExit(f"wsm-hardware-check: invalid {RELEASE_INFO}")
    return value


def source_commit() -> str | None:
    """Return HEAD only when ROOT is itself a Git work tree.

    A tarball extracted inside another repository must not inherit that
    repository's commit; in that case the release manifest is authoritative.
    """
    try:
        top = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if top.returncode != 0:
            return None
        if Path(top.stdout.strip()).resolve() != ROOT:
            return None
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
        requested_stat = requested.lstat()
    except FileNotFoundError:
        requested_stat = None
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot inspect output path: {exc}")
    if requested_stat is not None and stat.S_ISLNK(requested_stat.st_mode):
        raise SystemExit("wsm-hardware-check: output must be a real directory, not a symlink")

    for parent in requested.absolute().parents:
        try:
            parent_stat = parent.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(parent_stat.st_mode):
            raise SystemExit(f"wsm-hardware-check: output parent is a symlink: {parent}")

    try:
        output = requested.resolve(strict=False)
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot resolve output path: {exc}")

    for special in (Path("/dev"), Path("/proc"), Path("/sys")):
        if output == special or special in output.parents:
            raise SystemExit(f"wsm-hardware-check: output must not be under {special}")

    if output.is_symlink():
        raise SystemExit("wsm-hardware-check: output must be a real directory, not a symlink")

    if output.exists():
        if not output.is_dir():
            raise SystemExit("wsm-hardware-check: output must be a real directory")
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
    except OSError as exc:
        raise SystemExit(
            f"wsm-hardware-check: cannot secure output directory with mode 0700: {exc}"
        ) from exc

    try:
        actual_mode = stat.S_IMODE(output.stat(follow_symlinks=False).st_mode)
    except OSError as exc:
        raise SystemExit(
            f"wsm-hardware-check: cannot verify output directory permissions: {exc}"
        ) from exc
    if actual_mode != 0o700:
        raise SystemExit(
            "wsm-hardware-check: output directory permissions must be exactly 0700; "
            f"found {actual_mode:04o}"
        )
    return output


def redact(text: str, output: Path) -> str:
    return text.replace(str(output), "<out>")


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

    stdout = redact(result.stdout, output)
    stderr = redact(result.stderr, output)
    (output / f"{label}.stdout.log").write_text(stdout, encoding="utf-8")
    (output / f"{label}.stderr.log").write_text(stderr, encoding="utf-8")
    logged_args = [redact(arg, output) for arg in args]
    return {
        "argv": [Path(sys.executable).name, "-m", module, *logged_args],
        "exit_code": result.returncode,
        "stdout_log": f"{label}.stdout.log",
        "stderr_log": f"{label}.stderr.log",
    }


def read_existing_report(raw: str, output: Path) -> tuple[bytes, dict[str, Any]]:
    source = Path(raw).expanduser()
    try:
        info = source.lstat()
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot inspect report: {exc}")
    if stat.S_ISLNK(info.st_mode):
        raise SystemExit("wsm-hardware-check: report must be a regular file, not a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit("wsm-hardware-check: report must be a regular file")
    if info.st_size > MAX_REPORT_BYTES:
        raise SystemExit(f"wsm-hardware-check: report exceeds {MAX_REPORT_BYTES} bytes")

    try:
        report_bytes = source.read_bytes()
    except OSError as exc:
        raise SystemExit(f"wsm-hardware-check: cannot read report: {exc}")
    (output / "report.json").write_bytes(report_bytes)
    return report_bytes, {
        "argv": ["copy-existing-report", source.name],
        "exit_code": 0,
        "stdout_log": None,
        "stderr_log": None,
    }


def verify_plan(
    plan: dict[str, Any],
    report_bytes: bytes,
    backend: str,
) -> tuple[dict[str, Any], list[str]]:
    critical_errors: list[str] = []
    digest_errors: list[str] = []

    execution = plan.get("execution")
    if not isinstance(execution, dict):
        critical_errors.append("plan has no execution object")
    else:
        for key, expected in SAFE_EXECUTION.items():
            if execution.get(key) is not expected:
                critical_errors.append(f"execution.{key}={execution.get(key)!r}, expected {expected!r}")

    if plan.get("plan_status") != "diagnostic-only":
        critical_errors.append(f"plan_status={plan.get('plan_status')!r}, expected 'diagnostic-only'")
    if plan.get("plan_mode") != "dry-run":
        critical_errors.append(f"plan_mode={plan.get('plan_mode')!r}, expected 'dry-run'")

    readiness = plan.get("plan_readiness")
    confirmable_false = isinstance(readiness, dict) and readiness.get("confirmable") is False
    if not confirmable_false:
        critical_errors.append("plan_readiness.confirmable must be false")

    expected_backend_id = EXPECTED_BACKEND_IDS[backend]
    backend_object = plan.get("backend")
    backend_id = backend_object.get("id") if isinstance(backend_object, dict) else None
    if backend_id != expected_backend_id:
        critical_errors.append(f"backend.id={backend_id!r}, expected {expected_backend_id!r}")

    source = plan.get("source_report")
    report_matches = (
        isinstance(source, dict) and source.get("sha256") == sha256_bytes(report_bytes)
    )
    if not report_matches:
        digest_errors.append("source_report.sha256 does not match the exact report bytes")

    unsigned = dict(plan)
    stated_digest = unsigned.pop("plan_sha256", None)
    calculated = sha256_bytes(canonical_json(unsigned).encode("utf-8"))
    digest_matches = stated_digest == calculated
    if not digest_matches:
        digest_errors.append("plan_sha256 does not match canonical plan bytes")

    details = {
        "plan_status": plan.get("plan_status"),
        "backend_id": backend_id,
        "backend_id_matches_request": backend_id == expected_backend_id,
        "confirmable_false": confirmable_false,
        "source_report_sha256_matches": report_matches,
        "plan_sha256_matches": digest_matches,
        "safe_execution_flags": not critical_errors,
    }
    return details, critical_errors + digest_errors


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
        help="use an existing regular-file report instead of collecting locally (for QA only)",
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
        report_bytes, command_entry = read_existing_report(args.report, output)
        commands.append(command_entry)
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
        stderr_text = (output / entry["stderr_log"]).read_text(encoding="utf-8")
        stdout_text = (output / entry["stdout_log"]).read_text(encoding="utf-8")
        blocked_with_reason = (
            entry["exit_code"] == 3
            and BLOCKED_MARKER in stderr_text
            and not stdout_text.strip()
        )

        if blocked_with_reason and not plan_path.exists():
            plans[backend] = {
                "status": "safely-blocked",
                "reason_log": entry["stderr_log"],
                "verification_errors": [],
            }
            continue
        if entry["exit_code"] != 0 or not plan_path.exists():
            detail = f"exit={entry['exit_code']}"
            if entry["exit_code"] == 3 and not blocked_with_reason:
                detail += " without the expected blocker marker and empty stdout"
            errors.append(f"{backend}: no safe plan emitted ({detail})")
            plans[backend] = {
                "status": "failed",
                "reason_log": entry["stderr_log"],
                "verification_errors": [detail],
            }
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{backend}: emitted plan is not valid JSON: {exc}")
            plans[backend] = {"status": "failed", "verification_errors": [str(exc)]}
            continue
        details, plan_errors = verify_plan(plan, report_bytes, backend)
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
            "policy_assertions": {
                "network_used": False,
                "root_required": False,
                "block_device_access": False,
                "bootloader_or_firmware_changes": False,
                "backend_invoked": False,
            },
            "observed": {"run_as_root": os.geteuid() == 0},
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
