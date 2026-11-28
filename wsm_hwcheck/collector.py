# SPDX-License-Identifier: LicenseRef-Volnist
"""Read-only Linux hardware inventory for WSM's pre-install preflight.

This first collector reads sysfs and procfs only. It does not execute external
commands, access the network, load modules, install packages, or write to disks.
"""

from __future__ import annotations

import datetime as dt
import os
import platform as host_platform
import secrets
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .diagnostics import (
    KernelLogSnapshot,
    ModuleInventory,
    enrich_device_diagnostics,
    loaded_module_names,
    read_current_kernel_log,
    read_module_aliases,
    read_module_inventory,
)


VERSION = "0.3.0"

# The report schema version this collector implements. Optional additions are a
# minor bump; a 1.0.0 report stays readable because the frozen 1.0.0 schema is
# still published beside the current one. See docs/hardware/REPORT-FORMAT.md.
SCHEMA_VERSION = "1.1.0"

# Local, offline naming database. Optional and bounded: when none of these
# files exists, PCI devices keep their vendor:device ids and no model name is
# invented from the id.
PCI_IDS_PATHS = (
    "/usr/share/hwdata/pci.ids",
    "/usr/share/misc/pci.ids",
    "/usr/share/pci.ids",
    "/var/lib/pciutils/pci.ids",
)
PCI_IDS_MAX_BYTES = 16 * 1024 * 1024

# Only these machines have an unambiguous legacy-BIOS reading of "no EFI".
X86_MACHINES = frozenset({"x86_64", "amd64", "i386", "i486", "i586", "i686", "x86"})


def _read(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeError):
        return None
    if not value or value.lower() in {"unknown", "none", "n/a"}:
        return None
    return value


def _clean(value: str | None) -> str | None:
    """Drop placeholder strings a kernel or firmware writes instead of a value."""
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in {
        "unknown",
        "none",
        "n/a",
        "to be filled by o.e.m.",
        "to be filled by oem",
        "default string",
    }:
        return None
    return text


def _relative_sysfs(path: Path, sysfs_root: Path) -> str:
    try:
        return "/" + path.relative_to(sysfs_root).as_posix()
    except ValueError:
        return path.as_posix()


def _driver_facts(device_path: Path) -> dict[str, Any]:
    """Record which kernel driver is bound to a device, if any.

    A bound driver always creates the ``driver`` symlink in sysfs, including
    drivers built into the kernel. So for a device directory that exists, an
    absent symlink is a positive observation - nothing is bound - and not an
    unreadable source. Saying ``unknown`` there would hide the single fact the
    GPU certification question turns on.
    """
    if not device_path.is_dir():
        return {"status": "unknown"}

    driver_link = device_path / "driver"
    try:
        driver_path = driver_link.resolve(strict=True)
    except (OSError, RuntimeError):
        return {
            "status": "none-known",
            "notes": (
                "No driver symlink is present in sysfs for this device, so no "
                "driver was bound at collection time."
            ),
        }

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


def _int_read(path: Path) -> int | None:
    value = _read(path)
    if value is None:
        return None
    try:
        return int(value, 10)
    except ValueError:
        return None


def _bool_read(path: Path) -> bool | None:
    value = _read(path)
    if value is None:
        return None
    lowered = value.lower()
    if lowered in {"1", "y", "yes"}:
        return True
    if lowered in {"0", "n", "no"}:
        return False
    return None


def _hex_id(value: str | None) -> str | None:
    """Normalise a sysfs hex id (``0x10de``) to the ``10de`` form."""
    if not value:
        return None
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) != 4 or any(char not in "0123456789abcdef" for char in text):
        return None
    return text


def _boot_mode(sysfs_root: Path, architecture: str) -> tuple[str, str]:
    """Return (boot_mode, why), never guessing the firmware type.

    The kernel exposes EFI runtime services only when the firmware booted it
    through EFI, so the directory is positive evidence. Its absence is only
    meaningful on x86, where the alternative is a legacy BIOS/CSM handoff; on
    other architectures an absent directory proves nothing.
    """
    if (sysfs_root / "firmware" / "efi").is_dir():
        return (
            "uefi",
            "sysfs:/firmware/efi is present: the kernel was booted through EFI.",
        )
    if (
        architecture.lower() in X86_MACHINES
        and (sysfs_root / "class" / "dmi" / "id").is_dir()
    ):
        return (
            "bios",
            "sysfs:/firmware/efi is absent while x86 DMI identity is present: "
            "the firmware handed the kernel over in legacy BIOS/CSM mode.",
        )
    return (
        "unknown",
        "Neither sysfs:/firmware/efi nor an x86 DMI identity is available, "
        "so the boot mode is not determined.",
    )


def _normalise_bios_date(raw: str | None) -> str | None:
    """DMI writes MM/DD/YYYY; the schema field is a plain ISO date.

    An unparseable or placeholder date returns None so the field is omitted
    instead of carrying a vendor-specific string into a date-formatted field.
    """
    if not raw:
        return None
    value = raw.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(value, pattern).date()
        except ValueError:
            continue
        if not 1990 <= parsed.year <= dt.date.today().year + 1:
            return None
        return parsed.isoformat()
    return None


def parse_pci_ids(text: str) -> dict[str, tuple[str, str]]:
    """Parse the ``vendor:device`` naming table out of a pci.ids file.

    Only vendor and device names are kept; subsystem names and device classes
    are ignored because the report has no field for them and a partial table is
    more honest than a fabricated one.
    """
    table: dict[str, tuple[str, str]] = {}
    vendor: tuple[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("C ") or line.startswith("S "):
            vendor = None
            continue
        if line.startswith("\t\t"):
            continue
        if line.startswith("\t"):
            if vendor is None:
                continue
            identifier, _, name = line.strip().partition("  ")
            device_id = _hex_id(identifier)
            if device_id is None:
                continue
            table[f"{vendor[0]}:{device_id}"] = (vendor[1], name.strip())
            continue
        identifier, _, name = line.partition("  ")
        vendor_id = _hex_id(identifier.strip())
        vendor = (vendor_id, name.strip()) if vendor_id else None
    return table


def read_pci_ids(paths: Iterable[str | Path]) -> dict[str, tuple[str, str]] | None:
    """Read the first readable local pci.ids file, or None when none exists."""
    for path in paths:
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(PCI_IDS_MAX_BYTES)
        except OSError:
            continue
        table = parse_pci_ids(data.decode("utf-8", errors="replace"))
        if table:
            return table
    return None


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
        "bios_release": "bios_release",
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

    bios_date = _normalise_bios_date(_read(dmi / "bios_date"))
    if bios_date:
        facts["bios_date"] = bios_date
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


def _cpu_facts(
    fields: dict[str, str],
    logical_processors: int,
    sysfs_root: Path,
) -> dict[str, Any]:
    """Stepping and microcode revision, each recorded only when observed.

    Profile evidence expires when the microcode named in the report changes, so
    the applied revision is collected explicitly instead of being inferred from
    the model name. CPU flags are deliberately absent: the ISA level is a
    separate versioned contract (``wsm-cpu-isa/1``) and is not duplicated here.
    """
    facts: dict[str, Any] = {}
    unavailable: list[str] = []
    for source, target in (
        ("cpu family", "family"),
        ("model", "model_number"),
        ("stepping", "stepping"),
        ("microcode", "microcode"),
    ):
        value = fields.get(source)
        if value:
            facts[target] = value

    if "microcode" not in facts:
        # Some kernels omit the revision from /proc/cpuinfo; sysfs still exposes
        # the revision applied to each logical CPU.
        value = _read(
            sysfs_root / "devices" / "system" / "cpu" / "cpu0" / "microcode" / "version"
        )
        if value:
            facts["microcode"] = value
        else:
            unavailable.append("microcode")

    if logical_processors:
        facts["logical_processors"] = logical_processors
    else:
        unavailable.append("logical_processors")

    if unavailable:
        facts["unavailable"] = unavailable
    return facts


def _cpu_device(
    proc_root: Path,
    sysfs_root: Path,
    observed_at: str,
) -> dict[str, Any] | None:
    cpuinfo = _read(proc_root / "cpuinfo")
    if not cpuinfo:
        return None

    fields: dict[str, str] = {}
    logical_processors = 0
    for line in cpuinfo.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key == "processor":
            logical_processors += 1
        if key in {
            "model name",
            "vendor_id",
            "Hardware",
            "CPU implementer",
            "cpu family",
            "model",
            "stepping",
            "microcode",
        }:
            cleaned = _clean(value)
            if cleaned:
                fields.setdefault(key, cleaned)

    model = fields.get("model name") or fields.get("Hardware")
    manufacturer = fields.get("vendor_id") or fields.get("CPU implementer")
    if not model and not manufacturer:
        return None

    identity: dict[str, Any] = {}
    if model:
        identity["model"] = model
    if manufacturer:
        identity["manufacturer"] = manufacturer

    device = _device_base(
        device_id="cpu-0",
        category="cpu",
        bus="cpu",
        observed_at=observed_at,
        source="procfs:/cpuinfo",
        summary="CPU model information was read from procfs.",
        driver={"status": "not-applicable"},
        identity=identity,
    )
    cpu = _cpu_facts(fields, logical_processors, sysfs_root)
    if cpu:
        device["cpu"] = cpu
    return device


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


TRANSPORT_BY_SUBSYSTEM = (
    ("usb", "usb"),
    ("nvme", "nvme"),
    ("ata", "sata"),
    ("mmc", "mmc"),
    ("virtio", "virtio"),
    ("scsi", "scsi-other"),
)


def _storage_transport(entry: Path, device_path: Path, sysfs_root: Path) -> str | None:
    """Name the bus a block device really sits on, from its sysfs ancestry.

    ``/sys/block/sdX`` says nothing about SATA versus USB, and the installer
    cares about the difference. Ancestor subsystems answer it; when the chain
    cannot be resolved the fact stays unknown rather than being inferred from
    the kernel's device name.
    """
    try:
        start = device_path.resolve(strict=True)
    except (OSError, RuntimeError):
        start = device_path
    try:
        stop_at = sysfs_root.resolve()
    except (OSError, RuntimeError):
        stop_at = sysfs_root

    found: set[str] = set()
    for parent in (start, *start.parents):
        if parent != stop_at and stop_at not in parent.parents:
            break
        try:
            found.add((parent / "subsystem").resolve(strict=True).name)
        except (OSError, RuntimeError):
            continue
        if parent == stop_at:
            break

    for subsystem, transport in TRANSPORT_BY_SUBSYSTEM:
        if subsystem in found:
            return transport

    # Only names that are unambiguous on their own are accepted as a fallback.
    if entry.name.startswith("nvme"):
        return "nvme"
    if entry.name.startswith("mmc"):
        return "mmc"
    return None


def _storage_facts(entry: Path, device_path: Path, sysfs_root: Path) -> dict[str, Any]:
    """Size, sector sizes, medium type, partitions and transport of one disk.

    Every fact is optional. Whatever cannot be read is listed in ``unavailable``
    instead of being filled with a plausible default.
    """
    facts: dict[str, Any] = {}
    unavailable: list[str] = []

    sectors = _int_read(entry / "size")
    if sectors is None:
        unavailable.append("capacity_bytes")
    else:
        facts["capacity_bytes"] = sectors * 512

    for target, relative in (
        ("logical_block_size", "queue/logical_block_size"),
        ("physical_block_size", "queue/physical_block_size"),
    ):
        value = _int_read(entry / relative)
        if value is None:
            unavailable.append(target)
        else:
            facts[target] = value

    for target, relative in (
        ("rotational", "queue/rotational"),
        ("removable", "removable"),
        ("read_only", "ro"),
    ):
        value = _bool_read(entry / relative)
        if value is None:
            unavailable.append(target)
        else:
            facts[target] = value

    transport = _storage_transport(entry, device_path, sysfs_root)
    if transport is None:
        unavailable.append("transport")
    else:
        facts["transport"] = transport

    partitions: list[dict[str, Any]] = []
    try:
        children = sorted(entry.iterdir())
    except OSError:
        unavailable.append("partitions")
    else:
        for child in children:
            if not (child / "partition").is_file():
                continue
            partition: dict[str, Any] = {"name": child.name}
            number = _int_read(child / "partition")
            if number is not None:
                partition["number"] = number
            start = _int_read(child / "start")
            if start is not None:
                partition["start_sector"] = start
            length = _int_read(child / "size")
            if length is not None:
                partition["sectors"] = length
            partitions.append(partition)
        facts["partitions"] = partitions

    if unavailable:
        facts["unavailable"] = unavailable
    return facts


def _gpu_facts(device_path: Path) -> dict[str, Any]:
    """Boot-VGA flag, owned DRM nodes and PCIe link state of one GPU function."""
    facts: dict[str, Any] = {}
    unavailable: list[str] = []

    boot_vga = _bool_read(device_path / "boot_vga")
    if boot_vga is None:
        unavailable.append("boot_vga")
    else:
        facts["boot_vga"] = boot_vga

    drm = device_path / "drm"
    if drm.is_dir():
        try:
            facts["drm_cards"] = sorted(
                child.name for child in drm.iterdir() if child.name.startswith("card")
            )
        except OSError:
            unavailable.append("drm_cards")
    else:
        # No DRM directory means no KMS node is attached to this function; that
        # is not the same as an unreadable source, but it is also not proof that
        # the GPU cannot drive a display, so the fact stays unavailable.
        unavailable.append("drm_cards")

    link: dict[str, Any] = {}
    for target, filename in (
        ("current_speed", "current_link_speed"),
        ("max_speed", "max_link_speed"),
    ):
        value = _read(device_path / filename)
        if value:
            link[target] = value
        else:
            unavailable.append(f"pci_link.{target}")
    for target, filename in (
        ("current_width", "current_link_width"),
        ("max_width", "max_link_width"),
    ):
        value = _int_read(device_path / filename)
        if value is None:
            unavailable.append(f"pci_link.{target}")
        else:
            link[target] = value
    if link:
        facts["pci_link"] = link

    if unavailable:
        facts["unavailable"] = unavailable
    return facts


def _network_facts(device_path: Path, sysfs_root: Path) -> dict[str, Any]:
    """Link the network interfaces that sysfs attributes to this PCI function.

    The MAC address is never read: the report's privacy profile forbids it, and
    the model identity of a NIC is its vendor:device id plus driver, not its
    hardware address.
    """
    facts: dict[str, Any] = {"status": "unknown", "interfaces": []}
    net_root = sysfs_root / "class" / "net"
    try:
        entries = sorted(net_root.iterdir())
    except OSError:
        facts["unavailable"] = ["interfaces"]
        return facts

    try:
        owner = device_path.resolve(strict=True)
    except (OSError, RuntimeError):
        facts["unavailable"] = ["interfaces"]
        return facts

    facts["status"] = "observed"
    for entry in entries:
        try:
            backing = (entry / "device").resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if backing != owner:
            continue

        interface: dict[str, Any] = {"name": entry.name}
        for target, filename in (("operstate", "operstate"), ("duplex", "duplex")):
            value = _read(entry / filename)
            if value:
                interface[target] = value
        carrier = _bool_read(entry / "carrier")
        if carrier is not None:
            interface["carrier"] = carrier
        speed = _int_read(entry / "speed")
        if speed is not None and speed >= 0:
            interface["speed_mbps"] = speed
        mtu = _int_read(entry / "mtu")
        if mtu is not None and mtu > 0:
            interface["mtu"] = mtu
        facts["interfaces"].append(interface)

    return facts


def _pci_devices(
    sysfs_root: Path,
    observed_at: str,
    pci_names: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
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
            "device_id": "device",
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

        vendor_id = _hex_id(vendor)
        device_id = _hex_id(product)
        names = None
        if pci_names is not None and vendor_id and device_id:
            names = pci_names.get(f"{vendor_id}:{device_id}")
        if names:
            identity["manufacturer"] = names[0]
            identity["model"] = names[1]

        category = _pci_category(_read(entry / "class"))
        device = _device_base(
            device_id=f"pci-{entry.name}",
            category=category,
            bus="pci",
            observed_at=observed_at,
            source=f"sysfs:/bus/pci/devices/{entry.name}",
            summary="PCI function and its kernel driver binding were read from sysfs.",
            driver=_driver_facts(entry),
            identity=identity,
        )
        if names:
            device["evidence"].append({
                "kind": "database-record",
                "source": "pci.ids",
                "observed_at": observed_at,
                "confidence": "strong",
                "summary": (
                    f"The local pci.ids database names {vendor_id}:{device_id} as "
                    f"{names[0]} {names[1]}. The name is a label for the id: it "
                    "does not prove which card is installed or that it works."
                ),
            })
        if category == "gpu":
            device["gpu"] = _gpu_facts(entry)
        elif category == "network":
            device["network"] = _network_facts(entry, sysfs_root)
        devices.append(device)
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
            "device_id": product,
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
            summary="USB parent identity was read; interface-level class and driver binding are not collected.",
            driver={"status": "unknown"},
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

        device = _device_base(
            device_id=f"block-{entry.name}",
            category="storage-device",
            bus=bus,
            observed_at=observed_at,
            source=f"sysfs:/block/{entry.name}",
            summary=(
                "Block storage identity, driver binding and topology were read "
                "from sysfs; partition tables and filesystems are not read."
            ),
            driver=_driver_facts(device_path),
            identity=identity,
        )
        device["storage"] = _storage_facts(entry, device_path, sysfs_root)
        devices.append(device)
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
    *,
    include_runtime_diagnostics: bool = False,
    modules_root: str | Path = "/lib/modules",
    kernel_log_snapshot: KernelLogSnapshot | None = None,
    pci_ids_paths: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Collect a local-only report from read-only Linux pseudo-filesystems."""
    sysfs = Path(sysfs_root)
    proc = Path(proc_root)
    observed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    if observed_at.endswith("+00:00"):
        observed_at = observed_at[:-6] + "Z"

    architecture = host_platform.machine() or "unknown"
    platform_facts = _platform_facts(sysfs)
    boot_mode, boot_evidence = _boot_mode(sysfs, architecture)
    environment: dict[str, Any] = {
        "architecture": architecture,
        "kernel_release": _read(proc / "sys" / "kernel" / "osrelease") or host_platform.uname().release,
        "boot_mode": boot_mode,
        "boot_mode_evidence": boot_evidence,
        "virtualization": _virtualization(platform_facts, sysfs),
    }
    if platform_facts:
        environment["platform"] = platform_facts

    pci_names = read_pci_ids(PCI_IDS_PATHS if pci_ids_paths is None else pci_ids_paths)

    devices: list[dict[str, Any]] = []
    cpu = _cpu_device(proc, sysfs, observed_at)
    board = _board_device(platform_facts, observed_at)
    if cpu:
        devices.append(cpu)
    if board:
        devices.append(board)

    devices.extend(_pci_devices(sysfs, observed_at, pci_names))
    devices.extend(_usb_devices(sysfs, observed_at))
    devices.extend(_block_devices(sysfs, observed_at))
    devices.extend(_display_devices(sysfs, observed_at))

    collectors = [{
        "name": "wsm-hwcheck-sysfs",
        "version": VERSION,
        "available": True,
        "scope": "unprivileged-read-only",
        "notes": "Reads sysfs/procfs only. No network requests or system mutations.",
    }, {
        "name": "wsm-pci-ids-database",
        "available": pci_names is not None,
        "scope": "offline-database",
        "notes": (
            "Reads the local pci.ids file for vendor/device names. A name labels a "
            "PCI id; it does not prove which card is installed or that it works."
        ),
    }]
    warnings: list[str] = []
    if pci_names is None:
        warnings.append(
            "The local pci.ids naming database is unavailable; PCI devices carry "
            "vendor:device ids only and model names remain unknown."
        )

    if include_runtime_diagnostics:
        release = str(environment.get("kernel_release") or "")
        aliases_text: str | None = None
        module_root: Path | None = None
        if release and Path(release).name == release and release not in {".", ".."}:
            module_root = Path(modules_root) / release
            aliases_text = read_module_aliases(module_root / "modules.alias")
        module_inventory: ModuleInventory | None = (
            read_module_inventory(module_root) if module_root is not None else None
        )
        log_snapshot = (
            kernel_log_snapshot
            if kernel_log_snapshot is not None
            else read_current_kernel_log()
        )
        loaded_modules = loaded_module_names(sysfs / "module")

        for device in devices:
            if device.get("bus") not in {"pci", "usb"}:
                continue
            enrich_device_diagnostics(
                device,
                aliases_text=aliases_text,
                loaded_modules=loaded_modules,
                module_inventory=module_inventory,
                kernel_log=log_snapshot,
                observed_at=observed_at,
            )

        collectors.extend([
            {
                "name": "wsm-module-alias-database",
                "available": aliases_text is not None,
                "scope": "offline-database",
                "notes": (
                    "Reads the local modules.alias file for the running kernel; "
                    "matches are driver candidates, not proof of binding or functionality."
                ),
            },
            {
                "name": "wsm-current-boot-kernel-log",
                "available": log_snapshot.available,
                "scope": "unprivileged-read-only",
                "notes": (
                    "Streams the current-boot log with a 2 MiB tail cap and timeout; "
                    "raw log lines are not included in the report, and truncation is reported."
                ),
            },
            {
                "name": "wsm-installed-module-index",
                "available": module_inventory.available if module_inventory is not None else False,
                "scope": "offline-database",
                "notes": (
                    "Checks modules.dep paths against files on disk and records modules.builtin; "
                    f"modules.dep available={module_inventory.modules_dep_available if module_inventory is not None else False}, "
                    f"modules.builtin available={module_inventory.modules_builtin_available if module_inventory is not None else False}, "
                    f"complete={module_inventory.complete if module_inventory is not None else False}."
                ),
            },
        ])
        if aliases_text is None:
            warnings.append(
                "The current kernel module alias database is unavailable; unbound driver candidates remain unknown."
            )
        if not log_snapshot.available:
            warnings.append(
                "The current-boot kernel log is unavailable; runtime firmware state remains unknown."
            )
        if log_snapshot.truncated:
            warnings.append(
                "The current-boot kernel log exceeded the 2 MiB collector limit; only the bounded tail was analyzed."
            )
        if module_inventory is None or not module_inventory.complete:
            warnings.append(
                "The current kernel module indexes are incomplete; driver availability remains uncertain unless an existing sysfs binding or loaded module provides direct evidence."
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": "wsm-" + secrets.token_hex(12),
        "collected_at": observed_at,
        "environment": environment,
        "collectors": collectors,
        "devices": devices,
        "warnings": warnings,
        "limitations": [
            "Inventory and driver evidence do not prove end-to-end device functionality.",
            "Runtime firmware status remains unknown when the current-boot kernel log is unavailable or contains no device-attributable firmware event.",
            "A modules.alias match is a candidate only; it does not prove that a driver is bound or that a device function works.",
            "USB v0.1 records parent-device identity only; composite interface classes, per-interface driver bindings, and parent/interface relationships are not collected.",
            "Display v0.1 records DRM connector state and modes only; it does not decode EDID or establish a connector-to-GPU relationship.",
            "Boot mode is derived from sysfs:/firmware/efi; UEFI firmware booted through CSM is reported as bios, and a platform where neither source is readable stays unknown.",
            "PCI model names come from the local pci.ids file when one exists; the name labels a vendor:device id and does not prove the installed card, its revision or its function.",
            "Storage transport is derived from the sysfs ancestor subsystems of the block device; when the ancestry is not resolvable the fact is listed as unavailable instead of assumed.",
            "Network facts cover only interfaces whose sysfs device link resolves to the recorded PCI function; USB network interfaces and wireless association are not collected.",
            "Partition tables, filesystem types and bootloader entries are not read; only partition offsets and sizes exposed by sysfs are recorded.",
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
