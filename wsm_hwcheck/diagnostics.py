# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only driver and runtime-firmware evidence for WSM hardware preflight.

This module reports observations, not inferred device support:
- modules.alias can identify candidate modules for the current kernel;
- sysfs can show a driver binding or a loaded module;
- current-boot kernel logs can report runtime firmware load outcomes.

It never loads/unloads modules, installs packages, updates device firmware, or
sends hardware data over the network.
"""

from __future__ import annotations

import fnmatch
import os
import re
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

MAX_MODULES_ALIAS_BYTES = 8 * 1024 * 1024
MAX_MODULE_INDEX_BYTES = 32 * 1024 * 1024
MAX_KERNEL_LOG_BYTES = 2 * 1024 * 1024
MAX_KERNEL_LOG_LINES = 4096
MAX_KERNEL_LOG_STDERR_BYTES = 8 * 1024
_KERNEL_PIPE_CHUNK_BYTES = 64 * 1024
MAX_FIRMWARE_EVIDENCE = 20
_COMMAND_TIMEOUT_SECONDS = 3.0

_MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FIRMWARE_NAME_RE = re.compile(r"^[A-Za-z0-9_./+-]{1,160}$")
_DIRECT_LOAD_FAILURE_RE = re.compile(
    r"Direct firmware load for\s+(?P<blob>\S+)\s+failed with error\s+(?P<errno>-?\d+)",
    re.IGNORECASE,
)
_FIRMWARE_LOAD_FAILURE_RE = re.compile(
    r"failed to load firmware(?: file| blob)?\s+(?P<blob>\S+)",
    re.IGNORECASE,
)
_FIRMWARE_VERSION_OBSERVED_RE = re.compile(
    r"\bloaded firmware version\s+(?P<detail>[^\s,;]+)",
    re.IGNORECASE,
)
_FIRMWARE_DIRECT_LOADING_RE = re.compile(
    r"\bdirect-loading\s+(?P<blob>\S+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class KernelLogSnapshot:
    """Bounded output from the current boot's kernel log."""

    available: bool
    source: str
    lines: tuple[str, ...] = ()
    reason: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class ModuleInventory:
    """Local module artifacts corroborated by modules.dep and modules.builtin."""

    modules_dep_available: bool
    modules_builtin_available: bool
    installed_modules: frozenset[str]
    built_in_modules: frozenset[str]

    @property
    def available(self) -> bool:
        return self.modules_dep_available or self.modules_builtin_available

    @property
    def complete(self) -> bool:
        return self.modules_dep_available and self.modules_builtin_available


@dataclass(frozen=True)
class FirmwareLogResult:
    """Device-attributed runtime firmware evidence derived from kernel messages."""

    requirement: str
    runtime_status: str
    kernel_log_evidence: tuple[str, ...]


def read_module_aliases(path: str | Path) -> str | None:
    """Read a bounded, local modules.alias database; return None if unavailable."""
    alias_path = Path(path)
    try:
        if alias_path.stat().st_size > MAX_MODULES_ALIAS_BYTES:
            return None
        return alias_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _module_name_from_path(relative_path: str) -> str | None:
    """Extract a normalized module name from a safe kernel module relative path."""
    if not relative_path or relative_path.startswith("/"):
        return None
    parts = Path(relative_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None

    filename = parts[-1]
    for suffix in (".ko.zst", ".ko.xz", ".ko.gz", ".ko.bz2", ".ko.lz4", ".ko"):
        if filename.endswith(suffix):
            name = filename[:-len(suffix)]
            if _MODULE_NAME_RE.fullmatch(name):
                return _normalized_module_name(name)
            return None
    return None


def _read_bounded_text(path: Path, limit: int = MAX_MODULE_INDEX_BYTES) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_module_inventory(module_root: str | Path) -> ModuleInventory:
    """Read current-kernel module indexes and corroborate files without executing tools.

    modules.dep paths are checked for safe relative traversal and must resolve to
    an existing file inside the current kernel's module directory. modules.builtin
    is treated as evidence that the module is built into the kernel image.
    """
    root = Path(module_root)
    root_resolved: Path | None
    try:
        root_resolved = root.resolve(strict=True)
        if not root_resolved.is_dir():
            root_resolved = None
    except OSError:
        root_resolved = None

    dep_text = _read_bounded_text(root / "modules.dep") if root_resolved else None
    builtin_text = _read_bounded_text(root / "modules.builtin") if root_resolved else None
    installed: set[str] = set()
    builtins: set[str] = set()

    if dep_text is not None and root_resolved is not None:
        for line in dep_text.splitlines():
            relative_path = line.split(":", 1)[0].strip()
            name = _module_name_from_path(relative_path)
            if not name:
                continue
            try:
                resolved = (root / relative_path).resolve(strict=True)
                resolved.relative_to(root_resolved)
                if resolved.is_file():
                    installed.add(name)
            except (OSError, RuntimeError, ValueError):
                continue

    if builtin_text is not None:
        for line in builtin_text.splitlines():
            name = _module_name_from_path(line.strip())
            if name:
                builtins.add(name)

    return ModuleInventory(
        modules_dep_available=dep_text is not None,
        modules_builtin_available=builtin_text is not None,
        installed_modules=frozenset(installed),
        built_in_modules=frozenset(builtins),
    )


def parse_module_aliases(modalias: str | None, aliases_text: str | None) -> tuple[str, ...] | None:
    """Return sorted module candidates; None means the alias database was unavailable.

    The kernel-generated modules.alias file uses shell-style wildcard patterns.
    fnmatchcase is used only for this local metadata lookup; it does not execute
    shell commands or interpret user-supplied input as a command.
    """
    if aliases_text is None:
        return None
    if not isinstance(modalias, str) or not modalias.strip():
        return ()

    value = modalias.strip().casefold()
    matches: set[str] = set()
    for line in aliases_text.splitlines():
        fields = line.strip().split()
        if len(fields) != 3 or fields[0] != "alias":
            continue
        pattern, module = fields[1], fields[2]
        if not _MODULE_NAME_RE.fullmatch(module):
            continue
        if fnmatch.fnmatchcase(value, pattern.casefold()):
            matches.add(module)
    return tuple(sorted(matches))


def _normalized_module_name(value: str) -> str:
    return value.replace("-", "_").casefold()


def derive_driver_facts(
    existing: Mapping[str, Any] | None,
    *,
    modalias: str | None,
    aliases_text: str | None,
    loaded_modules: Iterable[str] = (),
    module_inventory: ModuleInventory | None = None,
) -> dict[str, Any]:
    """Combine current sysfs facts with the current kernel's module alias table.

    A bound driver always takes precedence. A modules.alias entry is only a
    candidate mapping. When the local module indexes are complete, the mapping
    is corroborated against modules.dep plus a file on disk or modules.builtin.
    This still does not prove end-to-end device functionality.
    """
    facts: dict[str, Any] = dict(existing or {"status": "unknown"})
    if not isinstance(facts.get("status"), str):
        facts["status"] = "unknown"

    candidates = parse_module_aliases(modalias, aliases_text)
    if candidates is None or not modalias:
        return facts

    if facts.get("status") == "bound" or facts.get("bound_driver"):
        if len(candidates) == 1:
            facts.setdefault("candidate", candidates[0])
        elif len(candidates) > 1:
            facts["notes"] = "Matching module-alias candidates: " + ", ".join(candidates)
        return facts

    loaded_names = {_normalized_module_name(name) for name in loaded_modules}
    loaded_candidates = tuple(
        name for name in candidates if _normalized_module_name(name) in loaded_names
    )

    if loaded_candidates:
        facts["status"] = "module-loaded-unbound"
        facts["module_loaded"] = True
        if len(loaded_candidates) == 1:
            facts["module"] = loaded_candidates[0]
        if len(candidates) == 1:
            facts["candidate"] = candidates[0]
        elif len(candidates) > 1:
            facts["notes"] = "Matching module-alias candidates: " + ", ".join(candidates)
    elif candidates:
        if module_inventory is not None and module_inventory.available:
            verified_modules = tuple(
                name for name in candidates
                if _normalized_module_name(name) in module_inventory.installed_modules
                or _normalized_module_name(name) in module_inventory.built_in_modules
            )
            if verified_modules:
                facts["status"] = "available-only"
                if len(verified_modules) == 1:
                    facts["candidate"] = verified_modules[0]
                facts["notes"] = (
                    "Candidate corroborated by the current kernel module index: "
                    + ", ".join(verified_modules)
                    + (" (built into the kernel)." if all(
                        _normalized_module_name(name) in module_inventory.built_in_modules
                        for name in verified_modules
                    ) else " (module file recorded in modules.dep and present on disk).")
                )
            elif module_inventory.complete:
                facts["status"] = "none-known"
                facts["notes"] = (
                    "modules.alias contains candidate mapping(s) "
                    + ", ".join(candidates)
                    + ", but none is corroborated by an installed module file or "
                    "modules.builtin entry in the current kernel tree."
                )
            else:
                facts["status"] = "available-only"
                if len(candidates) == 1:
                    facts["candidate"] = candidates[0]
                facts["notes"] = (
                    "modules.alias contains candidate mapping(s), but the available "
                    "module indexes are incomplete; module-file availability remains unknown."
                )
        else:
            facts["status"] = "available-only"
            if len(candidates) == 1:
                facts["candidate"] = candidates[0]
                facts["notes"] = (
                    "Candidate comes from modules.alias; the module file's presence "
                    "could not be verified because modules.dep/modules.builtin are unavailable."
                )
            else:
                facts["notes"] = (
                    "Matching modules.alias candidates: " + ", ".join(candidates)
                    + ". Module file availability could not be verified."
                )
    else:
        facts["status"] = "none-known"
        facts["notes"] = (
            "No module alias matched this device in the current kernel's "
            "modules.alias database; this is not a global incompatibility verdict."
        )

    return facts


def _safe_firmware_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().strip("\"':,;()[]{}")
    if cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")
    if not _FIRMWARE_NAME_RE.fullmatch(cleaned):
        return None
    if any(part == ".." for part in cleaned.split("/")):
        return None
    return cleaned[:160]


def _device_locator_matches(line: str, locator: str) -> bool:
    value = locator.strip()
    if not value:
        return False
    # Permit the kernel's USB interface suffix (1-2:1.0) but do not match 1-20
    # when the device locator is 1-2, or adjacent PCI functions.
    pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(value)}(?![A-Za-z0-9_.-])"
    return re.search(pattern, line, re.IGNORECASE) is not None


def parse_firmware_log(
    lines: Iterable[str],
    *,
    device_locator: str | None,
) -> FirmwareLogResult:
    """Parse device-attributed runtime firmware evidence conservatively.

    A generic "direct-loading" message proves only that the firmware file was
    read into the firmware buffer. A driver "loaded firmware version" message
    proves that the driver observed/parsed an image version. Neither proves the
    device accepted the image or initialized, so both map to
    available-not-confirmed-loaded, never to loaded. The loaded state is reserved
    for a future device-specific success signature with reviewed semantics.
    """
    if not device_locator:
        return FirmwareLogResult("unknown", "unknown", ())

    failures: list[tuple[str | None, int | None]] = []
    version_observations: list[str | None] = []
    direct_loading: list[str | None] = []

    for raw_line in lines:
        if not isinstance(raw_line, str) or not _device_locator_matches(raw_line, device_locator):
            continue

        direct_failure = _DIRECT_LOAD_FAILURE_RE.search(raw_line)
        generic_failure = _FIRMWARE_LOAD_FAILURE_RE.search(raw_line)
        if direct_failure:
            blob = _safe_firmware_name(direct_failure.group("blob"))
            try:
                error_number = int(direct_failure.group("errno"))
            except (TypeError, ValueError):
                error_number = None
            failures.append((blob, error_number))
            continue
        if generic_failure:
            failures.append((_safe_firmware_name(generic_failure.group("blob")), None))
            continue

        lowered = raw_line.casefold()
        if "firmware" in lowered and any(
            phrase in lowered
            for phrase in ("failed to load", "failed loading", "unable to load", "could not load")
        ):
            failures.append((None, None))
            continue

        direct_loading_match = _FIRMWARE_DIRECT_LOADING_RE.search(raw_line)
        if direct_loading_match:
            direct_loading.append(_safe_firmware_name(direct_loading_match.group("blob")))
            continue

        version_match = _FIRMWARE_VERSION_OBSERVED_RE.search(raw_line)
        if version_match:
            version_observations.append(
                _safe_firmware_name(version_match.group("detail"))
            )

    evidence: list[str] = []
    for blob, error_number in failures:
        if error_number == -2:
            summary = f"Runtime firmware blob missing: {blob or 'unspecified'} (kernel error -2)."
        else:
            code = f" (kernel error {error_number})" if error_number is not None else ""
            summary = f"Runtime firmware load failed: {blob or 'unspecified'}{code}."
        if summary not in evidence:
            evidence.append(summary)

    if failures:
        if all(error_number == -2 for _, error_number in failures):
            status = "missing"
        else:
            status = "load-error"
        requirement = "required"
    elif version_observations or direct_loading:
        status = "available-not-confirmed-loaded"
        requirement = "required"

        version_names = sorted({name for name in version_observations if name})
        if version_names:
            evidence.append(
                "Device driver reported firmware image version(s): "
                + ", ".join(version_names)
                + "; device acceptance and initialization remain unconfirmed."
            )
        elif version_observations:
            evidence.append(
                "Device driver reported a firmware image version, but the value could not be normalized; "
                "device acceptance and initialization remain unconfirmed."
            )

        direct_names = sorted({name for name in direct_loading if name})
        if direct_names:
            evidence.append(
                "Kernel logged the firmware blob being read into the request buffer: "
                + ", ".join(direct_names)
                + "; final device assignment and initialization remain unconfirmed."
            )
        elif direct_loading:
            evidence.append(
                "Kernel logged a direct-loading step, but the firmware name could not be normalized; "
                "final device assignment and initialization remain unconfirmed."
            )
    else:
        status = "unknown"
        requirement = "unknown"

    return FirmwareLogResult(
        requirement,
        status,
        tuple(evidence[:MAX_FIRMWARE_EVIDENCE]),
    )


def _append_bounded_tail(target: bytearray, chunk: bytes, limit: int) -> None:
    target.extend(chunk)
    overflow = len(target) - limit
    if overflow > 0:
        del target[:overflow]


def _kill_process(process: Any) -> None:
    """Best-effort process termination without racing an already-exited child."""
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass


def _run_bounded_readonly_command(
    command: list[str],
    *,
    popen_factory: Callable[..., Any],
    timeout: float,
) -> tuple[int, bytes, bytes, bool, bool]:
    """Stream stdout/stderr with bounded tail buffers and a hard wall-clock timeout."""
    process = popen_factory(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        close_fds=True,
    )
    if process.stdout is None or process.stderr is None:
        _kill_process(process)
        process.wait()
        raise OSError("command pipes were not created")

    stdout_tail = bytearray()
    stderr_tail = bytearray()
    stdout_bytes_seen = 0
    timed_out = False
    selector = selectors.DefaultSelector()

    try:
        for stream, label in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)

        deadline = time.monotonic() + max(timeout, 0.01)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _kill_process(process)
                break

            events = selector.select(min(remaining, 0.25))
            if not events:
                continue

            for key, _ in events:
                stream = key.fileobj
                try:
                    chunk = os.read(key.fd, _KERNEL_PIPE_CHUNK_BYTES)
                except BlockingIOError:
                    continue

                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue

                if key.data == "stdout":
                    stdout_bytes_seen += len(chunk)
                    _append_bounded_tail(stdout_tail, chunk, MAX_KERNEL_LOG_BYTES)
                else:
                    _append_bounded_tail(stderr_tail, chunk, MAX_KERNEL_LOG_STDERR_BYTES)

        try:
            returncode = process.wait(timeout=max(timeout, 0.1))
        except subprocess.TimeoutExpired:
            _kill_process(process)
            returncode = process.wait()
            timed_out = True

        return (
            returncode,
            bytes(stdout_tail),
            bytes(stderr_tail),
            timed_out,
            stdout_bytes_seen > MAX_KERNEL_LOG_BYTES,
        )
    except BaseException:
        _kill_process(process)
        try:
            process.wait(timeout=0.1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def read_current_kernel_log(
    *,
    popen_factory: Callable[..., Any] | None = None,
    which: Callable[[str], str | None] | None = None,
    timeout: float = _COMMAND_TIMEOUT_SECONDS,
) -> KernelLogSnapshot:
    """Read current-boot kernel logs with bounded streaming and fixed read-only commands.

    journalctl is preferred because it can scope the query to the current boot.
    dmesg is a fallback to the current kernel ring buffer. Stdout is never fully
    buffered: only its last MAX_KERNEL_LOG_BYTES are retained, stderr is capped,
    and each process is killed after the timeout. No shell is used.
    """
    popen = popen_factory or subprocess.Popen
    find = which or shutil.which
    attempts = (
        ("journalctl", ("-k", "-b", "--no-pager", "--output=cat", "--lines=4096")),
        ("dmesg", ("--color=never",)),
    )
    failures: list[str] = []

    for name, arguments in attempts:
        executable = find(name)
        if not executable:
            continue
        try:
            returncode, stdout, stderr, timed_out, truncated = _run_bounded_readonly_command(
                [executable, *arguments],
                popen_factory=popen,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            failures.append("timeout")
            continue
        except OSError:
            failures.append("unavailable")
            continue

        if timed_out:
            failures.append("timeout")
            continue
        if returncode != 0:
            failures.append(
                "permission-denied" if b"permission denied" in stderr.lower()
                else "command-failed"
            )
            continue

        all_lines = stdout.decode("utf-8", errors="replace").splitlines()
        line_truncated = len(all_lines) > MAX_KERNEL_LOG_LINES
        lines = tuple(all_lines[-MAX_KERNEL_LOG_LINES:])
        return KernelLogSnapshot(
            available=True,
            source=f"{name} current-boot kernel log",
            lines=lines,
            truncated=truncated or line_truncated,
        )

    reason = failures[-1] if failures else "not-installed"
    return KernelLogSnapshot(
        available=False,
        source="current-boot kernel log",
        reason=reason,
    )


def loaded_module_names(sys_module_root: str | Path) -> set[str]:
    """Return module names visible under the read-only /sys/module tree."""
    root = Path(sys_module_root)
    try:
        return {entry.name for entry in root.iterdir() if entry.is_dir()}
    except OSError:
        return set()


def enrich_device_diagnostics(
    device: dict[str, Any],
    *,
    aliases_text: str | None,
    loaded_modules: Iterable[str],
    module_inventory: ModuleInventory | None = None,
    kernel_log: KernelLogSnapshot,
    observed_at: str,
) -> None:
    """Enrich one report-local PCI/USB device with schema-v1 evidence in place."""
    identity = device.get("identity")
    if not isinstance(identity, dict):
        return

    modalias = identity.get("modalias")
    if isinstance(modalias, str) and modalias:
        driver = device.get("driver")
        device["driver"] = derive_driver_facts(
            driver if isinstance(driver, Mapping) else None,
            modalias=modalias,
            aliases_text=aliases_text,
            loaded_modules=loaded_modules,
            module_inventory=module_inventory,
        )
        candidates = parse_module_aliases(modalias, aliases_text)
        if candidates is not None:
            evidence = device.setdefault("evidence", [])
            if isinstance(evidence, list):
                if candidates:
                    summary = (
                        f"Current kernel modules.alias matched {len(candidates)} "
                        f"driver candidate(s): {', '.join(candidates)}."
                    )
                    confidence = "strong"
                else:
                    summary = (
                        "No driver candidate matched this modalias in the current "
                        "kernel modules.alias database; this is not a global "
                        "incompatibility verdict."
                    )
                    confidence = "limited"
                evidence.append({
                    "kind": "database-record",
                    "source": "modules.alias for the running kernel",
                    "observed_at": observed_at,
                    "confidence": confidence,
                    "summary": summary,
                })
                if module_inventory is not None and module_inventory.available:
                    verified_candidates = tuple(
                        name for name in candidates
                        if _normalized_module_name(name) in module_inventory.installed_modules
                        or _normalized_module_name(name) in module_inventory.built_in_modules
                    )
                    if verified_candidates:
                        evidence.append({
                            "kind": "database-record",
                            "source": "modules.dep plus on-disk file / modules.builtin",
                            "observed_at": observed_at,
                            "confidence": "confirmed",
                            "summary": (
                                "Current kernel module indexes corroborate candidate(s): "
                                + ", ".join(verified_candidates) + "."
                            ),
                        })
                    elif module_inventory.complete:
                        evidence.append({
                            "kind": "database-record",
                            "source": "modules.dep and modules.builtin",
                            "observed_at": observed_at,
                            "confidence": "limited",
                            "summary": (
                                "No modules.alias candidate was corroborated by a present "
                                "module file or built-in module entry."
                            ),
                        })

    local_path = identity.get("local_path")
    locator = Path(local_path).name if isinstance(local_path, str) else None
    if not kernel_log.available or not locator:
        return

    result = parse_firmware_log(kernel_log.lines, device_locator=locator)
    if not result.kernel_log_evidence:
        return

    firmware = device.get("firmware")
    if not isinstance(firmware, dict):
        firmware = {}
        device["firmware"] = firmware
    firmware["kernel_log_evidence"] = list(result.kernel_log_evidence)
    if result.runtime_status != "unknown":
        firmware["requirement"] = result.requirement
        firmware["runtime_status"] = result.runtime_status

    evidence = device.setdefault("evidence", [])
    if isinstance(evidence, list):
        observed = result.runtime_status != "unknown"
        if result.runtime_status == "available-not-confirmed-loaded":
            summary = (
                "Current-boot kernel log confirms firmware blob retrieval or driver image-version "
                "observation, but device acceptance and initialization remain unconfirmed."
            )
        elif observed:
            summary = (
                f"Current-boot kernel log reports runtime firmware state: {result.runtime_status}."
            )
        else:
            summary = (
                "Current-boot kernel log contains no conclusive runtime firmware result."
            )
        evidence.append({
            "kind": "kernel-log",
            "source": kernel_log.source,
            "observed_at": observed_at,
            "confidence": "confirmed" if observed else "limited",
            "summary": summary,
        })
