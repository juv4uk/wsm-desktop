# SPDX-License-Identifier: LicenseRef-Volnist
"""Calamares jobmodule: validate hardware evidence, then deploy WSM.

This module is deliberately thin. It does not partition, format or install by
itself: it calls the same modules the CLI calls, so there is one implementation
of every dangerous operation and Calamares is only the face of it.

The Calamares contract for a Python jobmodule is small:

* ``run()`` returns ``None`` on success;
* on failure it returns ``(message, details)`` - a short line for the user and
  a longer text for the log.

Everything here is written to fail closed. A missing report, an unresolved
blocker, an invalid evidence bundle or a missing acknowledgement produces a
tuple, never a silent success.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Calamares loads this file by path, so the package is not importable yet.
# Walk up until the repository (or an installation) that contains wsm_install
# is found, instead of guessing a fixed depth.
for _parent in Path(__file__).resolve().parents:
    if (_parent / "wsm_install").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

try:  # Calamares injects this at runtime; tests substitute it.
    import libcalamares
except ImportError:  # pragma: no cover - exercised only outside Calamares
    libcalamares = None


def _global(key: str, default=None):
    """Read a Calamares global storage key without assuming the API shape."""
    if libcalamares is None:
        return default
    storage = getattr(libcalamares, "globalstorage", None)
    if storage is None:
        return default
    try:
        value = storage.value(key)
    except Exception:  # noqa: BLE001 - Calamares raises its own types
        return default
    return default if value is None else value


def _logger():
    if libcalamares is None:
        return None
    return getattr(libcalamares, "utils", None)


def _log(message: str) -> None:
    utils = _logger()
    if utils is not None and hasattr(utils, "debug"):
        utils.debug(message)


def _read_report() -> tuple[dict | None, bytes | None, str | None]:
    """Use the report the preflight step produced, or make one now."""
    path_value = _global("wsmReportPath")
    if not path_value:
        return None, None, (
            "no hardware report was produced by the preflight step; "
            "WSM will not install on unverified hardware"
        )
    path = Path(str(path_value))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, f"cannot read hardware report {path}: {exc}"
    try:
        return json.loads(raw), raw, None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, None, f"hardware report {path} is not valid JSON: {exc}"


def _deploy(dry_run: bool) -> tuple[str, str] | None:
    """Build a preview only. APPLY stays disabled until the target contract is ratified."""
    if dry_run is not True:
        return (
            "WSM APPLY is disabled",
            "Calamares may preview a deployment plan, but it cannot perform disk writes yet.",
        )

    from wsm_install.executor import ExecutorError, execute
    from wsm_install.install_steps import backend_command, plan_steps, render
    from wsm_install.partition import Disk, Refused, plan as plan_layout

    report, _raw, error = _read_report()
    if error:
        return ("Hardware report is missing", error)

    disk_path = _global("wsmTargetDisk")
    if not disk_path:
        return (
            "No target disk was chosen",
            "Calamares did not pass a target disk; WSM never picks one itself.",
        )

    size = _global("wsmTargetSizeBytes")
    if not size:
        return (
            "Target disk size is unknown",
            "The size is how a swapped disk is detected, so it cannot be guessed.",
        )

    evidence_path = _global("wsmProfileEvidence")
    if evidence_path:
        from wsm_install.profile import EvidenceUnavailable, load, problems

        try:
            bundle = load(Path(str(evidence_path)))
        except EvidenceUnavailable as exc:
            return ("Hardware profile evidence cannot be read", str(exc))
        found = problems(bundle)
        if found:
            return (
                "Hardware profile evidence is not valid",
                "\n".join(found),
            )

    firmware = str(_global("firmwareType", "efi")).lower()
    firmware = "bios" if firmware in {"bios", "legacy"} else "uefi"

    try:
        layout = plan_layout(
            Disk(path=str(disk_path), size_bytes=int(size), has_existing_data=True),
            firmware,
            acknowledgement=str(disk_path) if not dry_run else str(disk_path),
            expected_size_bytes=int(size),
        )
        steps = plan_steps(layout)
        handoff = backend_command(layout, str(_global("wsmSystemFile", "systems/desktop.scm")))
    except Refused as exc:
        return ("WSM cannot use this disk", f"{exc.code}: {exc.message}")

    _log(render(steps, handoff))

    try:
        execute(
            steps,
            disk=str(disk_path),
            acknowledgement=str(disk_path),
            dry_run=True,
        )
    except ExecutorError as exc:
        return ("WSM deployment failed", f"{exc.code}: {exc.message}")

    return None


def run() -> tuple[str, str] | None:
    """Calamares entry point."""
    dry_run = _global("wsmDryRun", True)
    if not isinstance(dry_run, bool):
        return (
            "Invalid WSM dry-run setting",
            "wsmDryRun must be a boolean; no disk operation was attempted.",
        )
    if dry_run is not True:
        return (
            "WSM APPLY is disabled",
            "The Calamares frontend is preview-only until target identity, "
            "digest-bound consent, verified tools and QEMU acceptance are complete.",
        )

    _log("wsm_deploy: starting (dry_run=True; APPLY disabled)")
    result = _deploy(True)
    if result is not None:
        _log(f"wsm_deploy: failed: {result[0]}")
    return result


def pretty_name() -> str:
    return "Deploying WSM"
