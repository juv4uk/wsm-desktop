# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Linux hardware inventory for WSM's pre-install preflight.

This first collector reads sysfs and procfs only. It does not execute external
commands, access the network, load modules, install packages, or write to disks.
"""

from __future__ import annotations

import datetime as dt
import os
import platform as host_platform
import secrets
from pathlib import Path
from typing import Any


VERSION = "0.1.0"


def _read(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeError):
        return None
    if not value or value.lower() in {"unknown", "none", "n/a"}:
        return None
    return value


def _relative_sysfs(path: Path, sysfs_root: Path) -> str:
    try:
        return "/" + path.relative_to(sysfs_root).as_posix()
    except ValueError:
        return path.as_posix()


def _driver_facts(device_path: Path) -> dict[str, Any]:
    driver_link = device_path / "driver"
    try:
        driver_path = driver_link.resolve(strict=True)
    except (OSError, RuntimeError):
        return {"status": "unknown"}

    facts: dict[str, Any] = {
        "status": "bound",
        "bound_driver": driver_path.name,
    }
    module_link = driver_link / "module"
    try:
        module_path = module_link.resolve(strict=True)
    except (OSError, RuntimeError):
        # A bound driver may be built into the kernel; absence of a module
        # symlink is not evidence that the driver is missing.
        return facts

    facts["module"] = module_path.name
    facts["module_loaded"] = True
    return facts


def _firmware_unknown() -> dict[str, Any]:
    # v0.1 deliberately does not guess firmware requirements from device IDs.
    return {
        "requirement": "unknown",
        "runtime_status": "unknown",
        "redistribution_status": "unknown",
    }


def _evidence(source: str, summary: str, observed_at: str) -> list[dict[str, Any]]:
    return [{
        "kind": "live-observation",
        "source": source,
        "observed_at": observed_at,
        "confidence": "confirmed",
        "summary": summary,
    }]


def _device_base(
    *,
    device_id: str,
    category: str,
    bus: str,
    observed_at: str,
    source: str,
    summary: str,
    discovery_status: str = "discovered",
    criticality: list[str] | None = None,
    driver: dict[str, Any] | None = None,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "device_id": device_id,
        "category": category,
        "bus": bus,
        "discovery_status": discovery_status,
        "driver": driver or {"status": "unknown"},
        "firmware": _firmware_unknown(),
        "functional_tests": [],
        "evidence": _evidence(source, summary, observed_at),
        "recommendations": [],
    }
    if criticality:
        result["criticality"] = criticality
    if identity:
        result["identity"] = identity
    return result


def _platform_facts(sysfs_root: Path) -> dict[str, str]:
    dmi = sysfs_root / "class" / "dmi" / "id"
    mapping = {
        "sys_vendor": "system_vendor",
        "product_name": "product_name",
        "board_vendor": "board_vendor",
        "board_name": "board_name",
        "board_version": "board_version",
        "bios_vendor": "bios_vendor",
        "bios_version": "bios_version",
        "bios_date": "bios_date",
    }
    facts: dict[str, str] = {}
    for source_name, target_name in mapping.items():
        value = _read(dmi / source_name)
        if value and value.lower() not in {
            "to be filled by o.e.m.",
            "to be filled by oem",
            "default string",
        }:
            facts[target_name] = value
    return facts


def _virtualization(platform_facts: dict[str, str], sysfs_root: Path) -> str:
    hypervisor = _read(sysfs_root / "hypervisor" / "type")
    if hypervisor:
        value = hypervisor.lower()
        for candidate in ("kvm", "xen"):
            if candidate in value:
                return candidate

    combined = " ".join(
        platform_facts.get(key, "")
        for key in ("system_vendor", "product_name", "board_name")
    ).lower()
    if "qemu" in combined or "kvm" in combined:
        return "qemu"
    if "vmware" in combined:
        return "vmware"
    if "virtualbox" in combined or "innotek" in combined:
        return "other"
    if "virtual machine" in combined and "microsoft" in combined:
        return "hyper-v"
    if "xen" in combined:
        return "xen"
    return "unknown"


def _cpu_device(proc_root: Path, observed_at: str) -> dict[str, Any] | None:
    cpuinfo = _read(proc_root / "cpuinfo")
    if not cpuinfo:
        return None

    fields: dict[str, str] = {}
    for line in cpuinfo.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in {"model name", "vendor_id", "Hardware", "CPU implementer"}:
            fields.setdefault(key, value)

    model = fields.get("model name") or fields.get("Hardware")
    manufacturer = fields.get("vendor_id") or fields.get("CPU implementer")
    if not model and not manufacturer:
        return None

    identity: dict[str, Any] = {}
    if model:
        identity["model"] = model
    if manufacturer:
        identity["manufacturer"] = manufacturer

    return _device_base(
        device_id="cpu-0",
        category="cpu",
        bus="cpu",
        observed_at=observed_at,
        source="procfs:/cpuinfo",
        summary="CPU model information was read from procfs.",
        driver={"status": "not-applicable"},
        identity=identity,
    )


def _board_device(
    platform_facts: dict[str, str],
    observed_at: str,
) -> dict[str, Any] | None:
    vendor = platform_facts.get("board_vendor")
    model = platform_facts.get("board_name")
    if not vendor and not model:
        return None

    identity: dict[str, Any] = {}
    if vendor:
        identity["manufacturer"] = vendor
    if model:
        identity["model"] = model
    if platform_facts.get("board_version"):
        identity["revision"] = platform_facts["board_version"]

    return _device_base(
        device_id="platform-board-0",
        category="motherboard",
        bus="platform",
        observed_at=observed_at,
        source="sysfs:/class/dmi/id",
        summary="Motherboard identity fields were read from DMI sysfs.",
        driver={"status": "not-applicable"},
        identity=identity,
    )


def _pci_category(class_value: str | None) -> str:
    if not class_value:
        return "other"
    value = class_value.lower().removeprefix("0x")
    if value.startswith("03"):
        return "gpu"
    if value.startswith("02"):
        return "network"
    if value.startswith("04"):
        return "audio"
    if value.startswith("01"):
        return "storage-controller"
    if value.startswith("0c03"):
        return "usb-controller"
    return "other"


def _pci_devices(sysfs_root: Path, observed_at: str) -> list[dict[str, Any]]:
    root = sysfs_root / "bus" / "pci" / "devices"
    devices: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return devices

    for entry in entries:
        vendor = _read(entry / "vendor")
        product = _read(entry / "device")
        if not vendor and not product:
            continue
        identity: dict[str, Any] = {
            "local_path": _relative_sysfs(entry, sysfs_root),
        }
        fields = {
            "vendor_id": "vendor",
            "hardware_device_id": "device",
            "subsystem_vendor_id": "subsystem_vendor",
            "subsystem_device_id": "subsystem_device",
            "revision": "revision",
            "class_id": "class",
            "modalias": "modalias",
        }
        for target, source in fields.items():
            value = _read(entry / source)
            if value:
                identity[target] = value

        devices.append(_device_base(
            device_id=f"pci-{entry.name}",
            category=_pci_category(_read(entry / "class")),
            bus="pci",
            observed_at=observed_at,
            source=f"sysfs:/bus/pci/devices/{entry.name}",
            summary="PCI function and its kernel driver binding were read from sysfs.",
            driver=_driver_facts(entry),
            identity=identity,
        ))
    return devices


def _usb_category(class_value: str | None) -> str:
    if not class_value:
        return "other"
    value = class_value.lower().removeprefix("0x")
    if value == "02":
        return "network"
    if value == "03":
        return "input"
    if value == "08":
        return "storage-device"
    if value == "e0":
        return "bluetooth"
    return "other"


def _usb_devices(sysfs_root: Path, observed_at: str) -> list[dict[str, Any]]:
    root = sysfs_root / "bus" / "usb" / "devices"
    devices: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return devices

    for entry in entries:
        vendor = _read(entry / "idVendor")
        product = _read(entry / "idProduct")
        if not vendor or not product:
            continue
        identity: dict[str, Any] = {
            "vendor_id": vendor,
            "hardware_device_id": product,
            "local_path": _relative_sysfs(entry, sysfs_root),
        }
        for key, filename in (
            ("manufacturer", "manufacturer"),
            ("model", "product"),
            ("revision", "bcdDevice"),
            ("modalias", "modalias"),
        ):
            value = _read(entry / filename)
            if value:
                identity[key] = value

        devices.append(_device_base(
            device_id=f"usb-{entry.name}",
            category=_usb_category(_read(entry / "bDeviceClass")),
            bus="usb",
            observed_at=observed_at,
            source=f"sysfs:/bus/usb/devices/{entry.name}",
            summary="USB device identity and driver binding were read from sysfs.",
            driver=_driver_facts(entry),
            identity=identity,
        ))
    return devices


def _block_devices(sysfs_root: Path, observed_at: str) -> list[dict[str, Any]]:
    root = sysfs_root / "block"
    devices: list[dict[str, Any]] = []
    ignored_prefixes = ("loop", "ram", "zram", "dm-", "md", "sr")
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return devices

    for entry in entries:
        if entry.name.startswith(ignored_prefixes):
            continue
        device_path = entry / "device"
        if not device_path.exists():
            continue

        identity: dict[str, Any] = {
            "model": _read(device_path / "model") or entry.name,
            "local_path": _relative_sysfs(entry, sysfs_root),
        }
        vendor = _read(device_path / "vendor")
        if vendor:
            identity["manufacturer"] = vendor

        bus = "unknown"
        if entry.name.startswith("nvme"):
            bus = "nvme"
        elif entry.name.startswith("mmc"):
            bus = "mmc"
        elif entry.name.startswith("sd"):
            bus = "scsi"

        devices.append(_device_base(
            device_id=f"block-{entry.name}",
            category="storage-device",
            bus=bus,
            observed_at=observed_at,
            source=f"sysfs:/block/{entry.name}",
            summary="Block storage device and non-serial identity fields were read from sysfs.",
            driver=_driver_facts(device_path),
            identity=identity,
        ))
    return devices


def _display_devices(sysfs_root: Path, observed_at: str) -> list[dict[str, Any]]:
    root = sysfs_root / "class" / "drm"
    devices: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return devices

    for entry in entries:
        if "-" not in entry.name or not (entry / "status").exists():
            continue

        status = _read(entry / "status")
        modes_value = _read(entry / "modes")
        display: dict[str, Any] = {"connector": entry.name}
        if status in {"connected", "disconnected"}:
            display["connected"] = status == "connected"
        if modes_value:
            display["advertised_modes"] = [
                line.strip() for line in modes_value.splitlines() if line.strip()
            ]
        active_mode = _read(entry / "mode")
        if active_mode:
            display["active_mode"] = active_mode

        summary = f"DRM connector {entry.name} reports status {status or 'unknown'}."
        device = _device_base(
            device_id=f"display-{entry.name}",
            category="display",
            bus="edid",
            observed_at=observed_at,
            source=f"sysfs:/class/drm/{entry.name}",
            summary=summary,
            driver={"status": "not-applicable"},
        )
        device["display"] = display
        devices.append(device)
    return devices


def collect_report(
    sysfs_root: str | Path = "/sys",
    proc_root: str | Path = "/proc",
) -> dict[str, Any]:
    """Collect a local-only report from read-only Linux pseudo-filesystems."""
    sysfs = Path(sysfs_root)
    proc = Path(proc_root)
    observed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    if observed_at.endswith("+00:00"):
        observed_at = observed_at[:-6] + "Z"

    platform_facts = _platform_facts(sysfs)
    environment: dict[str, Any] = {
        "architecture": host_platform.machine() or "unknown",
        "kernel_release": _read(proc / "sys" / "kernel" / "osrelease") or host_platform.uname().release,
        "boot_mode": "uefi" if (sysfs / "firmware" / "efi").is_dir() else "unknown",
        "virtualization": _virtualization(platform_facts, sysfs),
    }
    if platform_facts:
        environment["platform"] = platform_facts

    devices: list[dict[str, Any]] = []
    cpu = _cpu_device(proc, observed_at)
    board = _board_device(platform_facts, observed_at)
    if cpu:
        devices.append(cpu)
    if board:
        devices.append(board)

    devices.extend(_pci_devices(sysfs, observed_at))
    devices.extend(_usb_devices(sysfs, observed_at))
    devices.extend(_block_devices(sysfs, observed_at))
    devices.extend(_display_devices(sysfs, observed_at))

    return {
        "schema_version": "1.0.0",
        "report_id": "wsm-" + secrets.token_hex(12),
        "collected_at": observed_at,
        "environment": environment,
        "collectors": [{
            "name": "wsm-hwcheck-sysfs",
            "version": VERSION,
            "available": True,
            "scope": "unprivileged-read-only",
            "notes": "Reads sysfs/procfs only. No subprocesses, network requests, or system mutations.",
        }],
        "devices": devices,
        "warnings": [],
        "limitations": [
            "v0.1.0 performs inventory only; it does not prove end-to-end device functionality.",
            "Firmware requirements and runtime firmware load status remain unknown until a dedicated kernel-log and firmware-path collector is reviewed.",
            "No remote hardware database lookup or probe upload is performed.",
        ],
        "privacy": {
            "profile": "strict-local",
            "network_upload_performed": False,
            "network_requests_performed": False,
            "sensitive_identifiers_included": False,
            "redactions_applied": [
                "serial-number", "mac-address", "uuid", "hostname",
                "username", "ip-address", "storage-wwn",
            ],
        },
    }
