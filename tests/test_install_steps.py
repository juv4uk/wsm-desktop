# SPDX-License-Identifier: LicenseRef-Volnist
"""Ordering and device naming: the two ways an install step list goes wrong."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.install_steps import (  # noqa: E402
    backend_command,
    device_for,
    plan_steps as _plan_steps,
    render,
    TRUSTED_TOOLS,
)
from wsm_install.partition import Disk, Layout, Refused, plan  # noqa: E402


def tool(step) -> str:
    """Basename of the command: paths are absolute, names are what we assert on."""
    return step.command[0].rsplit("/", 1)[-1]

# Unit tests also run on non-Guix CI hosts. Give the planner a disposable
# system-profile fixture rather than relying on the developer host or PATH.
_PROFILE_TMP = TemporaryDirectory(prefix="wsm-guix-tool-profile-")
_PROFILE_ROOT = Path(_PROFILE_TMP.name)
for _index, (_name, _binary) in enumerate(TRUSTED_TOOLS.items()):
    _directory = "bin" if _index % 2 == 0 else "sbin"
    _executable = _PROFILE_ROOT / _directory / _binary
    _executable.parent.mkdir(parents=True, exist_ok=True)
    _executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _executable.read_bytes() == b"#!/bin/sh\nexit 0\n"
    _executable.chmod(0o755)


def plan_steps(*args, **kwargs):
    kwargs.setdefault("profile_root", _PROFILE_ROOT)
    return _plan_steps(*args, **kwargs)


GIB = 1024 ** 3


def layout(firmware: str = "uefi", path: str = "/dev/nvme0n1"):
    disk = Disk(path, 256 * GIB, has_existing_data=True)
    return plan(disk, firmware, acknowledgement=path)


class DeviceNamingTests(unittest.TestCase):
    def test_nvme_partitions_get_a_p_suffix(self) -> None:
        self.assertEqual(device_for("/dev/nvme0n1", 2), "/dev/nvme0n1p2")

    def test_sata_partitions_do_not(self) -> None:
        self.assertEqual(device_for("/dev/sda", 2), "/dev/sda2")

    def test_mmc_partitions_get_a_p_suffix(self) -> None:
        self.assertEqual(device_for("/dev/mmcblk0", 1), "/dev/mmcblk0p1")


class LayoutConsentTests(unittest.TestCase):
    def test_plan_steps_rejects_layout_without_bound_acknowledgement(self) -> None:
        unconfirmed = Layout(firmware="uefi", disk="/dev/nvme0n1")
        with self.assertRaises(Refused) as caught:
            plan_steps(unconfirmed)
        self.assertEqual(caught.exception.code, "disk.acknowledgement")

    def test_backend_handoff_rejects_layout_without_recorded_disk_size(self) -> None:
        unconfirmed = layout()
        unconfirmed.disk_size_bytes = None
        with self.assertRaises(Refused) as caught:
            backend_command(unconfirmed, "systems/desktop.scm")
        self.assertEqual(caught.exception.code, "disk.size-unrecorded")


class OrderingTests(unittest.TestCase):
    def test_partition_table_is_reread_before_formatting(self) -> None:
        current = layout()
        commands = current.commands()
        steps = plan_steps(current)
        names = [tool(step) for step in steps]
        self.assertEqual(names[:len(commands)], ["sgdisk"] * len(commands))
        self.assertEqual(names[len(commands)], "partprobe")
        self.assertLess(names.index("partprobe"), names.index("mkfs.ext4"))

    def test_partition_table_argv_is_complete_and_destructive(self) -> None:
        current = layout()
        commands = current.commands()
        steps = plan_steps(current)[:len(commands)]
        expected = [
            [steps[index].command[0], *command[1:]]
            for index, command in enumerate(commands)
        ]
        self.assertEqual([step.command for step in steps], expected)
        self.assertTrue(all(step.destructive for step in steps))
        self.assertIn("--zap-all", steps[0].command)
        self.assertEqual(steps[0].command[-1], current.disk)

    def test_root_is_mounted_before_the_esp(self) -> None:
        steps = plan_steps(layout())
        mounts = [step.command for step in steps if tool(step) == "mount"]
        self.assertEqual(mounts[0][2], "/mnt")
        self.assertEqual(mounts[1][2], "/mnt/boot/efi")

    def test_esp_is_mounted_inside_the_target_not_outside(self) -> None:
        """An ESP mounted at /boot/efi puts the bootloader on the live system."""
        steps = plan_steps(layout())
        targets = [step.command[-1] for step in steps if tool(step) == "mount"]
        self.assertTrue(all(target.startswith("/mnt") for target in targets))

    def test_uefi_formats_a_fat32_esp(self) -> None:
        steps = plan_steps(layout("uefi"))
        fat = [step for step in steps if tool(step) == "mkfs.fat"]
        self.assertEqual(len(fat), 1)
        self.assertIn("32", fat[0].command)

    def test_bios_has_no_esp_step(self) -> None:
        steps = plan_steps(layout("bios", "/dev/sda"))
        self.assertFalse(any(tool(step) == "mkfs.fat" for step in steps))

    def test_destructive_steps_are_marked(self) -> None:
        steps = plan_steps(layout())
        destructive = [tool(step) for step in steps if step.destructive]
        self.assertIn("mkfs.ext4", destructive)
        self.assertIn("mkfs.fat", destructive)

    def test_mounting_is_not_marked_destructive(self) -> None:
        steps = plan_steps(layout())
        for step in steps:
            if tool(step) == "mount":
                self.assertFalse(step.destructive)


class PathHijackTests(unittest.TestCase):
    """Omarchy #8172: a privileged helper with an inherited PATH ran user code.

    Every step here is meant to run as root, so no step may rely on PATH.
    """

    def test_non_guix_host_can_build_symbolic_preview_without_executables(self) -> None:
        # A preview is data only and APPLY is disabled. Do not require host Guix
        # tools merely to inspect the proposed plan; explicit profile roots and
        # actual Guix System profiles still use strict resolution.
        missing_profile = Path("/nonexistent/wsm-system-profile-for-tests")
        with patch("wsm_install.install_steps.TRUSTED_PROFILE_ROOT", missing_profile):
            steps = _plan_steps(layout())
        self.assertTrue(steps)
        self.assertTrue(
            all(step.command[0] in TRUSTED_TOOLS.values() for step in steps),
            "non-Guix preview must contain only logical allowlisted tool names",
        )

    def test_every_command_starts_with_an_absolute_path(self) -> None:
        for firmware, disk in (("uefi", "/dev/nvme0n1"), ("bios", "/dev/sda")):
            steps = plan_steps(layout(firmware, disk))
            for step in steps:
                with self.subTest(firmware=firmware, command=step.command[0]):
                    self.assertTrue(
                        step.command[0].startswith("/"),
                        f"{step.command[0]!r} would be resolved through PATH",
                    )

    def test_no_command_is_a_bare_tool_name(self) -> None:
        bare = {"sgdisk", "partprobe", "udevadm", "mount", "mkdir", "mkfs.ext4", "mkfs.fat"}
        for step in plan_steps(layout()):
            self.assertNotIn(step.command[0], bare)


class FilesystemChoiceTests(unittest.TestCase):
    def test_btrfs_and_xfs_are_refused_until_guix_config_matches(self) -> None:
        for filesystem in ("btrfs", "xfs"):
            with self.subTest(filesystem=filesystem):
                with self.assertRaises(Refused) as caught:
                    plan_steps(layout(), filesystem=filesystem)
                self.assertEqual(caught.exception.code, "filesystem.unsupported")

    def test_supported_filesystem_matches_guix_root_declaration(self) -> None:
        import re

        from wsm_install.install_steps import FILESYSTEMS, ROOT_FILESYSTEM

        scheme = (ROOT / "systems" / "desktop.scm").read_text(encoding="utf-8")
        root = re.search(
            r'\(file-system\s+\(mount-point "/".*?\(type "([^"]+)"\)',
            scheme,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(root, "desktop Guix system must declare a root filesystem")
        self.assertEqual(ROOT_FILESYSTEM, root.group(1))
        self.assertEqual(set(FILESYSTEMS), {root.group(1)})

    def test_unknown_filesystem_is_refused(self) -> None:
        with self.assertRaises(Refused) as caught:
            plan_steps(layout(), filesystem="ntfs")
        self.assertEqual(caught.exception.code, "filesystem.unsupported")

    def test_root_target_is_refused(self) -> None:
        with self.assertRaises(Refused) as caught:
            plan_steps(layout(), target="/")
        self.assertEqual(caught.exception.code, "target.unsafe")


class BackendCommandTests(unittest.TestCase):
    def test_command_shape(self) -> None:
        command = backend_command(layout(), "systems/desktop.scm")
        self.assertEqual(command, ["guix", "system", "init", "systems/desktop.scm", "/mnt"])

    def test_non_scheme_file_is_refused(self) -> None:
        with self.assertRaises(Refused):
            backend_command(layout(), "systems/desktop.json")


class RenderTests(unittest.TestCase):
    def test_render_warns_and_marks_destructive_steps(self) -> None:
        text = render(plan_steps(layout()), backend_command(layout(), "systems/desktop.scm"))
        self.assertIn("NOT EXECUTED", text)
        self.assertIn("DESTRUCTIVE", text)
        self.assertIn("guix system init", text)




class ForeignDataTests(unittest.TestCase):
    """Omarchy #14949: a reset deleted other operating systems' boot entries.

    The register in docs/LESSONS-FROM-OMARCHY.md calls this row `partial`,
    because "the ESP is mounted inside the target" proves where it is mounted,
    not whose ESP it is. The stronger property is different and testable
    without a VM: WSM never reuses somebody else's partition. The plan wipes the
    whole target disk and formats only partitions it created in that same plan,
    so there is no shared ESP to damage in the first place.
    """

    def test_whole_disk_is_wiped_before_any_partition_is_created(self) -> None:
        commands = layout().commands()
        self.assertEqual(commands[0], ["sgdisk", "--zap-all", layout().disk])

    def test_only_self_created_partitions_are_formatted_or_mounted(self) -> None:
        """Any /dev path in the step list must be ours, not a foreign partition."""
        current = layout()
        created = {device_for(current.disk, partition["number"]) for partition in current.partitions}
        allowed = created | {current.disk}
        for step in plan_steps(current):
            for argument in step.command:
                if argument.startswith("/dev/"):
                    self.assertIn(
                        argument,
                        allowed,
                        f"{argument!r} is not a partition this plan created",
                    )

    def test_the_plan_never_touches_the_firmware_boot_order(self) -> None:
        """Boot order is a separate claim; nothing here may quietly rewrite it."""
        tools = {step.command[0].rsplit("/", 1)[-1] for step in plan_steps(layout())}
        self.assertFalse(
            tools & {"efibootmgr", "bootctl", "grub-install", "grub2-install"},
            f"unexpected boot-order tooling: {sorted(tools)}",
        )


if __name__ == "__main__":
    unittest.main()
