#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Compare the three fact groups of two hardware reports, field by field.

The Free Pascal port in ``tools/pascal/wsm_hwcheck_slice.lpr`` is a first
vertical slice: it collects the
boot mode, the GPU record and the BIOS release/date, and nothing else. This
script is the only place where "the port agrees with the Python collector" is
decided. It takes two JSON reports - one produced by ``python -m wsm_hwcheck``,
one produced by the Pascal binary, both against the *same* synthetic sysfs tree
- and compares exactly those three groups.

What it compares
----------------
``boot_mode``
    ``environment.boot_mode`` and ``environment.boot_mode_evidence``.
``bios``
    ``environment.platform.bios_release`` and ``environment.platform.bios_date``.
``gpu``
    Every device whose ``category`` is ``gpu``, in report order, reduced to
    ``device_id``, ``bus``, ``discovery_status``, the identity fields a sysfs
    read can supply (``local_path``, ``vendor_id``, ``device_id``,
    ``subsystem_vendor_id``, ``subsystem_device_id``, ``revision``,
    ``class_id``, ``modalias``), the ``driver`` object, and the whole ``gpu``
    object (``boot_vga``, ``drm_cards``, ``pci_link``, ``unavailable``).

A key that is present on one side and absent on the other is a difference, not
a skip: absence is compared as the sentinel ``<missing>``. Array order is
compared, because ``drm_cards`` and ``unavailable`` are ordered lists in the
report.

What it deliberately cannot compare
-----------------------------------
* ``identity.manufacturer`` and ``identity.model``, and the ``database-record``
  evidence item they justify. Those come from the local ``pci.ids`` naming
  database, which is outside this slice: the Pascal program does not read it.
  They are excluded by name and the exclusion is printed on every run, so it
  cannot be mistaken for agreement.
* ``collected_at``, ``report_id``, ``collectors``, ``warnings``, ``limitations``
  and ``privacy`` - bookkeeping, not facts, and two collectors cannot share a
  timestamp or a random id.
* Every fact group the slice does not port: CPU, USB, block/storage, display,
  network, and the runtime diagnostics (module aliases, kernel log, module
  index).
* Whether either program reads a *real* ``/sys`` correctly. Both are fed the
  same synthetic tree; agreement there proves the algorithms match, not that
  the fixtures resemble the owner's H170 board.

Usage::

    check_fpc_parity.py PYTHON_REPORT.json PASCAL_REPORT.json [--schema S]
    check_fpc_parity.py --emit-fixtures DIRECTORY

Exit status: 0 agreement, 1 disagreement, 2 the comparison could not be made.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GROUPS = ("boot_mode", "bios", "gpu")

IDENTITY_FIELDS = (
    "local_path",
    "vendor_id",
    "device_id",
    "subsystem_vendor_id",
    "subsystem_device_id",
    "revision",
    "class_id",
    "modalias",
)
DRIVER_FIELDS = ("status", "bound_driver", "module", "module_loaded", "notes")
GPU_FIELDS = ("boot_vga", "drm_cards", "pci_link", "unavailable")

# Fields a sysfs read cannot produce. Named here, printed on every run, and
# never compared - see the module docstring.
NOT_COMPARED = {
    "identity": ("manufacturer", "model"),
}


class _Missing:
    """A key that one report has and the other does not."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Missing)

    def __hash__(self) -> int:
        return hash("<missing>")


MISSING = _Missing()


def _group_field(container: object, key: str):
    if not isinstance(container, dict):
        return MISSING
    return container.get(key, MISSING)


def _reduced(container: object, required: tuple[str, ...], excluded: tuple[str, ...] = ()):
    """Every key of ``container`` except the excluded ones, plus the required ones.

    Keys are taken from the document as well as from ``required`` so an
    unexpected extra field shows up as a difference instead of being ignored.
    """
    if not isinstance(container, dict):
        return {name: MISSING for name in required}
    names = (set(required) | set(container)) - set(excluded)
    return {name: container.get(name, MISSING) for name in sorted(names)}


def boot_mode_group(report: object) -> dict:
    environment = _group_field(report, "environment")
    return {
        "boot_mode": _group_field(environment, "boot_mode"),
        "boot_mode_evidence": _group_field(environment, "boot_mode_evidence"),
    }


def bios_group(report: object) -> dict:
    environment = _group_field(report, "environment")
    platform = _group_field(environment, "platform")
    return {
        "bios_release": _group_field(platform, "bios_release"),
        "bios_date": _group_field(platform, "bios_date"),
    }


def gpu_group(report: object) -> list:
    devices = _group_field(report, "devices")
    if not isinstance(devices, list):
        return []
    result = []
    for device in devices:
        if _group_field(device, "category") != "gpu":
            continue
        result.append(
            {
                "device_id": _group_field(device, "device_id"),
                "bus": _group_field(device, "bus"),
                "discovery_status": _group_field(device, "discovery_status"),
                "identity": _reduced(
                    _group_field(device, "identity"),
                    IDENTITY_FIELDS,
                    NOT_COMPARED["identity"],
                ),
                "driver": _reduced(_group_field(device, "driver"), DRIVER_FIELDS),
                "gpu": _reduced(_group_field(device, "gpu"), GPU_FIELDS),
            }
        )
    return result


def groups_of(report: object) -> dict:
    return {
        "boot_mode": boot_mode_group(report),
        "bios": bios_group(report),
        "gpu": gpu_group(report),
    }


def _join(path: str, step: object) -> str:
    if isinstance(step, int):
        return f"{path}[{step}]" if path else f"[{step}]"
    return f"{path}.{step}" if path else str(step)


def differences(left: object, right: object, path: str = "") -> list[str]:
    """Every leaf where the two values disagree, as ``path: a != b`` lines."""
    if isinstance(left, dict) and isinstance(right, dict):
        found: list[str] = []
        for key in sorted(set(left) | set(right)):
            found.extend(
                differences(
                    left.get(key, MISSING),
                    right.get(key, MISSING),
                    _join(path, key),
                )
            )
        return found
    if isinstance(left, list) and isinstance(right, list):
        found = []
        if len(left) != len(right):
            found.append(
                f"{path or '<root>'}: length {len(left)} != {len(right)} "
                f"({left!r} != {right!r})"
            )
        for index in range(min(len(left), len(right))):
            found.extend(differences(left[index], right[index], _join(path, index)))
        return found
    if isinstance(left, bool) != isinstance(right, bool):
        return [f"{path}: {left!r} != {right!r}"]
    if left != right:
        return [f"{path}: {left!r} != {right!r}"]
    return []


def compare(python_report: object, pascal_report: object) -> list[str]:
    """Differences between the two reports, limited to the three groups."""
    left = groups_of(python_report)
    right = groups_of(pascal_report)
    found: list[str] = []
    for name in GROUPS:
        for line in differences(left[name], right[name], name):
            found.append(line)
    return found


def render_mismatch(found: list[str], python_name: str, pascal_name: str) -> str:
    lines = [
        f"FPC-PARITY-FAIL: {len(found)} difference(s) between "
        f"{python_name} (python) and {pascal_name} (pascal)",
        "Format: <group>[<index>].<field>: <python value> != <pascal value>",
    ]
    lines.extend(f"  {line}" for line in found)
    lines.append(
        "Not compared by design: identity.manufacturer, identity.model (pci.ids "
        "labels), collected_at, report_id, collectors, warnings, limitations, "
        "privacy, and every fact group outside boot_mode/bios/gpu."
    )
    return "\n".join(lines)


def render_agreement(python_name: str, pascal_name: str) -> str:
    return "\n".join(
        [
            f"FPC-PARITY-PASS: {python_name} (python) and {pascal_name} (pascal) "
            "agree on boot_mode, bios and gpu",
            "Compared: boot_mode{boot_mode,boot_mode_evidence}, "
            "bios{bios_release,bios_date}, gpu[device_id,bus,discovery_status,"
            "identity(sysfs fields),driver,gpu]",
            "Not compared by design: identity.manufacturer, identity.model "
            "(pci.ids labels), collected_at, report_id, collectors, warnings, "
            "limitations, privacy, and every fact group outside the slice.",
        ]
    )


# --- synthetic fixtures ---------------------------------------------------
#
# These trees reproduce the synthetic sysfs used by tests/test_hwcheck.py, so
# that the Pascal program and the Python collector are fed byte-identical
# inputs. They are written to disk rather than created in-process because the
# Pascal binary can only read a filesystem.


def _write(root: Path, relative: str, value: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _uefi_tree(sysfs: Path, proc: Path) -> None:
    _write(proc, "sys/kernel/osrelease", "6.12.0-test\n")
    _write(
        proc,
        "cpuinfo",
        "processor : 0\nvendor_id : GenuineIntel\nmodel name : Example Intel CPU\n",
    )
    _write(sysfs, "firmware/efi/fw_platform_size", "64\n")
    _write(sysfs, "class/dmi/id/sys_vendor", "Example Vendor\n")
    _write(sysfs, "class/dmi/id/product_name", "Example Desktop\n")
    _write(sysfs, "class/dmi/id/board_vendor", "Example Board Co.\n")
    _write(sysfs, "class/dmi/id/board_name", "Example H170 Board\n")
    _write(sysfs, "class/dmi/id/board_version", "1.0\n")
    _write(sysfs, "class/dmi/id/bios_vendor", "Example BIOS Vendor\n")
    _write(sysfs, "class/dmi/id/bios_version", "F99-example\n")
    _write(sysfs, "class/dmi/id/bios_release", "5.12\n")
    # DMI writes MM/DD/YYYY; the report field is a plain ISO date.
    _write(sysfs, "class/dmi/id/bios_date", "01/15/2021\n")

    gpu = sysfs / "bus/pci/devices/0000:00:02.0"
    _write(gpu, "vendor", "0x8086\n")
    _write(gpu, "device", "0x1912\n")
    _write(gpu, "subsystem_vendor", "0x1458\n")
    _write(gpu, "subsystem_device", "0xd000\n")
    _write(gpu, "revision", "0x07\n")
    _write(gpu, "class", "0x030000\n")
    _write(gpu, "modalias", "pci:v00008086d00001912\n")
    _write(gpu, "boot_vga", "1\n")
    _write(gpu, "current_link_speed", "8.0 GT/s PCIe\n")
    _write(gpu, "max_link_speed", "8.0 GT/s PCIe\n")
    _write(gpu, "current_link_width", "16\n")
    _write(gpu, "max_link_width", "16\n")
    # A render node is not a card node and must not be listed in drm_cards.
    (gpu / "drm/card0").mkdir(parents=True)
    (gpu / "drm/renderD128").mkdir(parents=True)

    driver = sysfs / "bus/pci/drivers/i915"
    module = sysfs / "module/i915"
    driver.mkdir(parents=True)
    module.mkdir(parents=True)
    (driver / "module").symlink_to(module, target_is_directory=True)
    (gpu / "driver").symlink_to(driver, target_is_directory=True)

    # A second PCI function that is not a GPU: the slice must not report it.
    audio = sysfs / "bus/pci/devices/0000:00:1f.3"
    _write(audio, "vendor", "0x8086\n")
    _write(audio, "device", "0xa170\n")
    _write(audio, "class", "0x040300\n")


def _bios_tree(sysfs: Path, proc: Path) -> None:
    """Legacy-BIOS handoff, a GPU with nothing bound, and DMI placeholders."""
    _write(proc, "sys/kernel/osrelease", "6.12.0-test\n")
    _write(proc, "cpuinfo", "processor : 0\nmodel name : Example Intel CPU\n")
    # No firmware/efi directory at all: on x86 that is a positive observation.
    _write(sysfs, "class/dmi/id/sys_vendor", "Example Vendor\n")
    _write(sysfs, "class/dmi/id/product_name", "Example Desktop\n")
    _write(sysfs, "class/dmi/id/board_vendor", "Example Board Co.\n")
    _write(sysfs, "class/dmi/id/board_name", "Example H170 Board\n")
    _write(sysfs, "class/dmi/id/bios_vendor", "Example BIOS Vendor\n")
    _write(sysfs, "class/dmi/id/bios_version", "F98-example\n")
    # A placeholder is not a value: bios_release must be absent, not guessed.
    _write(sysfs, "class/dmi/id/bios_release", "To be filled by O.E.M.\n")
    # No bios_date file at all: the field must be absent.

    gpu = sysfs / "bus/pci/devices/0000:01:00.0"
    _write(gpu, "vendor", "0x10de\n")
    _write(gpu, "device", "0x1c82\n")
    _write(gpu, "class", "0x030000\n")
    _write(gpu, "modalias", "pci:v000010DEd00001C82\n")
    # No driver symlink, no boot_vga, no drm directory, no link attributes.


def _empty_tree(sysfs: Path, proc: Path) -> None:
    sysfs.mkdir(parents=True, exist_ok=True)
    proc.mkdir(parents=True, exist_ok=True)


FIXTURES = {
    "uefi": _uefi_tree,
    "bios": _bios_tree,
    "empty": _empty_tree,
}


def emit_fixtures(root: Path) -> list[str]:
    """Write every synthetic tree under ``root``; return the fixture names."""
    root.mkdir(parents=True, exist_ok=True)
    for name, builder in FIXTURES.items():
        sysfs = root / name / "sys"
        proc = root / name / "proc"
        sysfs.mkdir(parents=True, exist_ok=True)
        proc.mkdir(parents=True, exist_ok=True)
        builder(sysfs, proc)
    return sorted(FIXTURES)


def _load(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _validate(report: object, schema_path: Path, name: str) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ModuleNotFoundError:
        return [f"{name}: jsonschema is not installed, so the schema was not checked"]
    with schema_path.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{name}: schema {list(error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(report)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_fpc_parity",
        description=(
            "Compare the boot_mode, bios and gpu fact groups of a Python and a "
            "Free Pascal wsm-hwcheck report."
        ),
    )
    parser.add_argument("python_report", nargs="?", metavar="PYTHON.json")
    parser.add_argument("pascal_report", nargs="?", metavar="PASCAL.json")
    parser.add_argument(
        "--schema",
        metavar="PATH",
        help="also validate both reports against this JSON schema",
    )
    parser.add_argument(
        "--emit-fixtures",
        metavar="DIRECTORY",
        help="write the synthetic sysfs/proc trees used by tests/test_hwcheck.py",
    )
    args = parser.parse_args(argv)

    if args.emit_fixtures:
        names = emit_fixtures(Path(args.emit_fixtures))
        print(f"FPC-PARITY-FIXTURES: wrote {', '.join(names)} under {args.emit_fixtures}")
        return 0

    if not args.python_report or not args.pascal_report:
        parser.error("two report paths are required, or use --emit-fixtures")

    python_path = Path(args.python_report)
    pascal_path = Path(args.pascal_report)
    try:
        python_report = _load(python_path)
        pascal_report = _load(pascal_path)
    except (OSError, ValueError) as error:
        print(f"FPC-PARITY-ERROR: {error}", file=sys.stderr)
        return 2

    if args.schema:
        problems = _validate(python_report, Path(args.schema), python_path.name)
        problems += _validate(pascal_report, Path(args.schema), pascal_path.name)
        if problems:
            print(
                "FPC-PARITY-ERROR: a report is not schema-valid, so its groups "
                "cannot be trusted:\n  " + "\n  ".join(problems),
                file=sys.stderr,
            )
            return 2

    found = compare(python_report, pascal_report)
    if found:
        print(render_mismatch(found, python_path.name, pascal_path.name), file=sys.stderr)
        return 1
    print(render_agreement(python_path.name, pascal_path.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
