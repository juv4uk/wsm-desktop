# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only boot/service-manager evidence for systemd and GNU Shepherd."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from wsm_hwcheck.collector import collect_report

SCHEMA = "wsm-boot-profile/2"
VERSION = "0.2.0"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 60.0
MAX_OUTPUT_BYTES = 64 * 1024

# System-manager executables must never be selected from an inherited, user-writable PATH.
# Guix System exposes its trusted package profile here; standard systemd hosts use /usr/bin.
SYSTEM_EXECUTABLE_PATH = os.pathsep.join(
    ("/run/current-system/profile/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
)

# Fixed argument allowlists. No shell, user-supplied unit names or arbitrary argv.
SYSTEMD_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("version", ("--version",)),
    ("time", ("--no-pager", "time")),
    ("blame", ("--no-pager", "blame")),
    ("critical_chain_default", ("--no-pager", "critical-chain")),
    (
        "critical_chain_graphical",
        ("--no-pager", "critical-chain", "graphical.target"),
    ),
)
SHEPHERD_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("version", ("--version",)),
    ("status", ("status",)),
    ("log", ("log",)),
    ("graph", ("graph",)),
)
# Backward-compatible name for existing systemd-focused test fixtures.
COMMANDS = SYSTEMD_COMMANDS

SYSTEMD_WARNINGS = (
    "systemd-analyze time ends when services have been spawned; it does not prove "
    "that every service finished initialization or that the disk is idle.",
    "systemd-analyze blame measures activating time, omits Type=simple and queue "
    "waits, and does not account for parallel execution.",
    "critical-chain shows a time-critical dependency path, not all parallel work; "
    "socket activation, device units, jobs and timeouts have documented limitations.",
    "Firmware/loader timings may be reported when the bootloader exports EFI "
    "LoaderTime values; their absence means unknown, not zero. This collector "
    "does not read or write EFI variables directly.",
    "This artifact is one observation of the current boot, not a five-run sample "
    "or a complete desktop-readiness measurement.",
)
SHEPHERD_WARNINGS = (
    "herd status is a snapshot of the services visible through the current "
    "Shepherd socket; it is not a historical boot timeline.",
    "herd log reports the event history retained by the current Shepherd instance; "
    "it is not guaranteed to cover the complete boot if history was rotated or "
    "collection started after services were already running.",
    "herd graph reports service dependencies, not measured critical-path duration "
    "or proof that a graphical desktop session is ready.",
    "When run as a non-root user, herd observes that user's Shepherd instance, "
    "not the PID 1 system manager. The manager scope is recorded explicitly; "
    "the collector never invokes sudo or escalates privileges.",
    "Current-boot status/log/graph do not observe shutdown ordering, prove that "
    "service stop handlers completed, or confirm that filesystems were unmounted. "
    "The locked Free Guix source defines Shepherd 1.0.9; this collection does not prove "
    "that the built image or running manager uses that package.",
    "This artifact is one observation of the current boot, not a five-run sample "
    "or a complete desktop-readiness measurement.",
)


def _detect_manager(proc_root: Path) -> str:
    """Identify the init/service manager from PID 1 without guessing."""
    try:
        name = (proc_root / "1/comm").read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeError):
        return "unknown"
    return name if name in {"systemd", "shepherd"} else "unknown"


def _manager_scope(manager: str) -> str:
    """Describe which manager instance herd/systemd-analyze will observe."""
    if manager == "systemd":
        return "system"
    if manager == "shepherd":
        try:
            return "system" if os.geteuid() == 0 else "user"
        except AttributeError:
            return "unknown"
    return "unknown"


def _collection_status(
    commands: dict[str, dict[str, Any]],
    required: tuple[str, ...],
) -> str:
    if not required:
        return "unavailable"
    successful = sum(commands.get(name, {}).get("status") == "success" for name in required)
    if successful == len(required) and all(
        result.get("status") == "success" for result in commands.values()
    ):
        return "available"
    if successful:
        return "partial"
    return "unavailable"


def _bounded_text(value: str | bytes | None) -> tuple[str, bool]:
    if value is None:
        return "", False
    if isinstance(value, bytes):
        raw = value
    else:
        raw = value.encode("utf-8", errors="replace")
    truncated = len(raw) > MAX_OUTPUT_BYTES
    if truncated:
        raw = raw[:MAX_OUTPUT_BYTES]
    return raw.decode("utf-8", errors="replace"), truncated


def _command_result(
    program: str,
    argv: tuple[str, ...],
    executable: str | None,
    timeout_seconds: float,
    runner: Callable[..., Any],
) -> dict[str, Any]:
    normalized_argv = [program, *argv]
    if executable is None:
        return {
            "status": "unavailable",
            "reason": "command-not-found",
            "argv": normalized_argv,
            "exit_code": None,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    command = [executable, *argv]
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    # Do not let an inherited socket override redirect herd away from PID 1.
    environment.pop("SHEPHERD_SOCKET", None)
    started = time.monotonic()
    try:
        completed = runner(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=environment,
        )
        duration = max(0.0, time.monotonic() - started)
        stdout, stdout_truncated = _bounded_text(completed.stdout)
        stderr, stderr_truncated = _bounded_text(completed.stderr)
        successful = completed.returncode == 0
        return {
            "status": "success" if successful else "failed",
            "reason": None if successful else "non-zero-exit",
            "argv": normalized_argv,
            "exit_code": completed.returncode,
            "duration_seconds": duration,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    except subprocess.TimeoutExpired as exc:
        duration = max(0.0, time.monotonic() - started)
        stdout, stdout_truncated = _bounded_text(exc.stdout)
        stderr, stderr_truncated = _bounded_text(exc.stderr)
        return {
            "status": "timeout",
            "reason": "command-timeout",
            "argv": normalized_argv,
            "exit_code": None,
            "duration_seconds": duration,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "reason": "command-not-found",
            "argv": normalized_argv,
            "exit_code": None,
            "duration_seconds": max(0.0, time.monotonic() - started),
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
    except OSError:
        return {
            "status": "unavailable",
            "reason": "execution-error",
            "argv": normalized_argv,
            "exit_code": None,
            "duration_seconds": max(0.0, time.monotonic() - started),
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def _boot_identity(proc_root: Path) -> dict[str, Any]:
    source = "/proc/sys/kernel/random/boot_id"
    try:
        raw = (proc_root / "sys/kernel/random/boot_id").read_text(
            encoding="utf-8"
        ).strip()
    except (OSError, UnicodeError):
        return {"status": "unknown", "source": source, "digest": None}
    if not raw:
        return {"status": "unknown", "source": source, "digest": None}
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {"status": "available", "source": source, "digest": digest}


def _uptime_seconds(proc_root: Path) -> float | None:
    try:
        raw = (proc_root / "uptime").read_text(encoding="utf-8").split()
        value = float(raw[0])
    except (OSError, UnicodeError, ValueError, IndexError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _virtualization_evidence() -> dict[str, str]:
    try:
        report = collect_report()
    except (OSError, ValueError, TypeError):
        return {"detected": "unknown", "source": "unknown"}

    environment = report.get("environment")
    detected = (
        environment.get("virtualization")
        if isinstance(environment, dict)
        else None
    )
    if not isinstance(detected, str) or not detected.strip():
        detected = "unknown"

    source = "unknown"
    collectors = report.get("collectors")
    if isinstance(collectors, list):
        for collector in collectors:
            if (
                isinstance(collector, dict)
                and collector.get("name") == "wsm-hwcheck-sysfs"
            ):
                name = collector.get("name")
                version = collector.get("version")
                if isinstance(name, str) and isinstance(version, str):
                    source = f"{name}/{version}"
                break
    return {"detected": detected.strip().lower(), "source": source}


def collect_boot_profile(
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    proc_root: Path = Path("/proc"),
    *,
    runner: Callable[..., Any] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Collect one read-only boot profile from the manager that actually runs PID 1."""
    if (
        not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"timeout must be greater than 0 and at most {MAX_TIMEOUT_SECONDS:g} seconds"
        )

    manager = _detect_manager(proc_root)
    scope = _manager_scope(manager)
    command_runner = runner or subprocess.run
    executable_lookup = which or shutil.which

    if manager == "systemd":
        program = "systemd-analyze"
        command_set = SYSTEMD_COMMANDS
        required = ("time", "blame", "critical_chain_default")
        warnings = SYSTEMD_WARNINGS
    elif manager == "shepherd":
        program = "herd"
        command_set = SHEPHERD_COMMANDS
        required = ("status", "log", "graph")
        warnings = list(SHEPHERD_WARNINGS)
        if scope == "user":
            warnings.append(
                "The current process is unprivileged: service data belongs to the "
                "user Shepherd instance, not the system-wide Guix boot."
            )
    else:
        program = None
        command_set = ()
        required = ()
        warnings = (
            "PID 1 is neither systemd nor GNU Shepherd, or /proc/1/comm is unavailable. "
            "No substitute manager was guessed and no command was executed.",
            "This artifact is one observation of the current boot, not a five-run sample "
            "or a complete desktop-readiness measurement.",
        )

    if program is None:
        executable = None
    elif scope == "system":
        # Root observes PID 1. Do not resolve a privileged executable through
        # the inherited PATH: an earlier user-writable directory could replace it.
        executable = executable_lookup(program, path=SYSTEM_EXECUTABLE_PATH)
    else:
        # User Shepherd is deliberately unprivileged and may live in the user's
        # Guix/Home profile, so resolve it in that user's own PATH.
        executable = executable_lookup(program)
    commands = {
        name: _command_result(program, args, executable, timeout_seconds, command_runner)
        for name, args in command_set
    }
    collection_status = _collection_status(commands, required)

    observation_scope = (
        "user-service-manager"
        if manager == "shepherd" and scope == "user"
        else "system-boot" if manager in {"systemd", "shepherd"} and scope == "system"
        else "unknown"
    )
    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scope": observation_scope,
        "collection_status": collection_status,
        "manager": {
            "name": manager,
            "scope": scope,
            "detection_source": "/proc/1/comm",
        },
        "boot_identity": _boot_identity(proc_root),
        "uptime_seconds": _uptime_seconds(proc_root),
        "environment": {
            "kernel_release": platform.release(),
            "machine": platform.machine(),
            "virtualization": _virtualization_evidence(),
        },
        "commands": commands,
        "warnings": list(warnings),
    }
