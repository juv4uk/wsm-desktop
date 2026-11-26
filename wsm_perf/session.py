# SPDX-License-Identifier: LicenseRef-Volnist
"""Record the KDE Plasma autostart phase-2 session milestone."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping

SCHEMA = "wsm-desktop-session-readiness/1"
VERSION = "0.1.0"
MARKER = "plasma-autostart-phase-2"
LOGINCTL_TIMEOUT_SECONDS = 5.0
MAX_LOGINCTL_OUTPUT_BYTES = 4096
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{16}$")


class SessionReadinessError(ValueError):
    """The session marker cannot safely record this invocation."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _read_boot_digest(proc_root: Path) -> str | None:
    try:
        value = (proc_root / "sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
    except (OSError, UnicodeError):
        return None
    if not value:
        return None
    return _digest(value)


def _bounded_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    raw = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    if len(raw) > MAX_LOGINCTL_OUTPUT_BYTES:
        raise SessionReadinessError("login manager returned oversized session metadata")
    return raw.decode("utf-8", errors="replace")


def _parse_login_properties(output: str) -> tuple[str | None, int | None]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in {"Id", "TimestampMonotonic"}:
            continue
        if key in properties:
            raise SessionReadinessError("login manager returned duplicate session properties")
        properties[key] = value.strip()

    session_id = properties.get("Id")
    if session_id is not None and not _SESSION_ID.fullmatch(session_id):
        raise SessionReadinessError("login manager returned an invalid session identifier")

    raw_timestamp = properties.get("TimestampMonotonic")
    if raw_timestamp is None or not raw_timestamp.isdecimal():
        return session_id, None
    timestamp = int(raw_timestamp)
    if timestamp <= 0:
        return session_id, None
    return session_id, timestamp


def _login_session_start(
    environment: Mapping[str, str],
    *,
    runner: Callable[..., Any],
    which: Callable[[str], str | None],
) -> tuple[str | None, int | None, str | None]:
    raw_session_id = environment.get("XDG_SESSION_ID")
    if raw_session_id:
        if not _SESSION_ID.fullmatch(raw_session_id):
            return None, None, "invalid-session-id"
        session_ref = raw_session_id
    else:
        # loginctl's "self" resolves the session containing this process.
        session_ref = "self"

    executable = which("loginctl")
    if executable is None:
        return None, None, "loginctl-not-found"

    command = [
        executable,
        "show-session",
        session_ref,
        "--property=Id",
        "--property=TimestampMonotonic",
    ]
    command_environment = os.environ.copy()
    command_environment.update(environment)
    command_environment["LC_ALL"] = "C"
    command_environment["LANG"] = "C"
    try:
        completed = runner(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LOGINCTL_TIMEOUT_SECONDS,
            check=False,
            env=command_environment,
        )
    except subprocess.TimeoutExpired:
        return None, None, "loginctl-timeout"
    except OSError:
        return None, None, "loginctl-execution-error"

    if completed.returncode != 0:
        return None, None, "loginctl-nonzero-exit"
    try:
        session_id, timestamp = _parse_login_properties(_bounded_text(completed.stdout))
        if session_id is None:
            return None, None, "session-id-unavailable"
        if raw_session_id and session_id != raw_session_id:
            return None, None, "session-id-mismatch"
        return session_id, timestamp, None
    except SessionReadinessError:
        return None, None, "loginctl-invalid-output"


def collect_session_readiness(
    *,
    environment: Mapping[str, str] | None = None,
    proc_root: Path = Path("/proc"),
    runner: Callable[..., Any] | None = None,
    which: Callable[[str], str | None] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """Capture the point at which Plasma reaches X-KDE-autostart-phase 2.

    The elapsed value is login-session creation to this marker. It is not a
    claim that every service, device, or application is ready.
    """
    env = dict(os.environ if environment is None else environment)
    desktops = {
        item.strip().upper()
        for item in env.get("XDG_CURRENT_DESKTOP", "").split(":")
        if item.strip()
    }
    kde_session = env.get("KDE_FULL_SESSION", "").lower() == "true"
    if "KDE" not in desktops and not kde_session:
        raise SessionReadinessError("this marker is only valid inside a KDE Plasma session")

    clock = monotonic_ns or (lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC))
    # Capture immediately on entry: running loginctl first would inflate the
    # phase-2 marker by the helper's own startup and D-Bus round-trip time.
    phase2_monotonic_us = clock() // 1000

    command_runner = runner or subprocess.run
    executable_lookup = which or shutil.which
    session_id, login_start_us, login_error = _login_session_start(
        env,
        runner=command_runner,
        which=executable_lookup,
    )
    elapsed_ms: float | None = None
    warnings: list[str] = []

    if login_start_us is None:
        warnings.append(
            "The logind/elogind session start timestamp is unavailable; "
            "login-to-phase-2 latency remains unknown."
        )
    elif phase2_monotonic_us < login_start_us:
        warnings.append(
            "The login manager timestamp is later than the phase-2 clock sample; "
            "latency remains unknown."
        )
        login_start_us = None
    else:
        elapsed_ms = round((phase2_monotonic_us - login_start_us) / 1000.0, 3)

    if login_error:
        warnings.append(f"Session start evidence unavailable: {login_error}.")

    session_type = env.get("XDG_SESSION_TYPE", "").lower()
    if session_type not in {"x11", "wayland"}:
        session_type = "unknown"

    kde_version = env.get("KDE_SESSION_VERSION", "")
    if not kde_version.isdecimal() or len(kde_version) > 8:
        kde_version = ""

    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
        "status": "available" if elapsed_ms is not None else "partial",
        "marker": MARKER,
        "phase": 2,
        "session": {
            "type": session_type,
            "desktop": "KDE",
            "desktop_version": kde_version or None,
        },
        "timing": {
            "clock": "CLOCK_MONOTONIC",
            "source": "org.freedesktop.login1.Session.TimestampMonotonic",
            "session_start_monotonic_us": login_start_us,
            "phase2_monotonic_us": phase2_monotonic_us,
            "login_to_phase2_ms": elapsed_ms,
        },
        "boot_identity": {
            "digest": _read_boot_digest(proc_root),
        },
        "warnings": warnings,
    }


def _validate_private_directory(path: Path, *, uid: int, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise SessionReadinessError(f"{label} is unavailable: {exc.strerror}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SessionReadinessError(f"{label} must be a real directory, not a symlink")
    if metadata.st_uid != uid:
        raise SessionReadinessError(f"{label} is not owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SessionReadinessError(f"{label} must not be accessible by group or others")


def write_session_readiness(
    artifact: Mapping[str, Any],
    *,
    runtime_dir: Path,
    uid: int | None = None,
) -> Path:
    """Atomically write a 0600 artifact below the caller's private runtime dir."""
    owner = os.geteuid() if uid is None else uid
    runtime = Path(runtime_dir)
    if not runtime.is_absolute():
        raise SessionReadinessError("XDG_RUNTIME_DIR must be an absolute path")
    _validate_private_directory(runtime, uid=owner, label="XDG_RUNTIME_DIR")

    target_dir = runtime / "wsm"
    try:
        target_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise SessionReadinessError(f"cannot create WSM runtime directory: {exc.strerror}") from exc
    _validate_private_directory(target_dir, uid=owner, label="WSM runtime directory")

    boot_digest = artifact.get("boot_identity", {}).get("digest")
    if boot_digest is not None and not _HEX_DIGEST.fullmatch(boot_digest):
        raise SessionReadinessError("artifact contains an invalid boot digest")
    phase2_monotonic_us = artifact.get("timing", {}).get("phase2_monotonic_us")
    if (
        isinstance(phase2_monotonic_us, bool)
        or not isinstance(phase2_monotonic_us, int)
        or phase2_monotonic_us <= 0
    ):
        raise SessionReadinessError("artifact contains an invalid phase-2 monotonic timestamp")
    filename = f"plasma-phase2-{boot_digest or 'unknown'}-{phase2_monotonic_us}.json"
    destination = target_dir / filename
    fd, temporary_name = tempfile.mkstemp(prefix=".plasma-phase2-", dir=target_dir)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(artifact, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(target_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        try:
            os.close(fd)
        except OSError:
            pass
        raise SessionReadinessError(f"cannot store session-readiness artifact: {exc.strerror}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return destination
