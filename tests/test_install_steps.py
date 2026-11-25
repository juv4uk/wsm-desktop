# SPDX-License-Identifier: LicenseRef-Volnist
"""Ordering and device naming: the two ways an install step list goes wrong."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.install_steps import (  # noqa: E402
    CHANNEL_LOCK_PATH,
    SYSTEM_CONFIG_PATH,
    TARGET_MOUNTPOINT,
    TRUSTED_TOOLS,
    backend_command,
    device_for,
    plan_steps,
    render,
)
from wsm_install.partition import Disk, Refused, minimum_disk_size_bytes, plan  # noqa: E402


def tool(step) -> str:
    """Basename of the command: paths are absolute, names are what we assert on."""
    return step.command[0].rsplit("/", 1)[-1]

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


class OrderingTests(unittest.TestCase):
    def test_partition_table_is_reread_before_formatting(self) -> None:
        steps = plan_steps(layout())
        names = [tool(step) for step in steps]
        self.assertEqual(names[:3], ["sgdisk", "sgdisk", "sgdisk"])
        self.assertLess(max(i for i, name in enumerate(names) if name == "sgdisk"), names.index("partprobe"))
        self.assertLess(names.index("partprobe"), names.index("udevadm"))
        self.assertLess(names.index("udevadm"), names.index("mkfs.ext4"))

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
        self.assertTrue(any("--typecode=1:ef02" in step.command for step in steps if tool(step) == "sgdisk"))

    def test_destructive_steps_are_marked(self) -> None:
        steps = plan_steps(layout())
        destructive = [tool(step) for step in steps if step.destructive]
        self.assertEqual(destructive.count("sgdisk"), 3)
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

    def test_sgdisk_uses_absolute_guix_profile_path(self) -> None:
        steps = plan_steps(layout())
        first = next(step for step in steps if tool(step) == "sgdisk")
        self.assertEqual(first.command[0], TRUSTED_TOOLS["sgdisk"])
        self.assertEqual(first.command[0], "/run/current-system/profile/sbin/sgdisk")

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
    def test_btrfs_and_xfs_are_refused_until_the_typed_plan_supports_them(self) -> None:
        for filesystem in ("btrfs", "xfs"):
            with self.subTest(filesystem=filesystem), self.assertRaises(Refused) as caught:
                plan_steps(layout(), filesystem=filesystem)
            self.assertEqual(caught.exception.code, "filesystem.unsupported")

    def test_ext4_remains_the_supported_root_filesystem(self) -> None:
        steps = plan_steps(layout(), filesystem="ext4")
        mkfs = [step for step in steps if tool(step) == "mkfs.ext4"]
        self.assertEqual(len(mkfs), 1)
        self.assertIn("-F", mkfs[0].command)

    def test_unknown_filesystem_is_refused(self) -> None:
        with self.assertRaises(Refused) as caught:
            plan_steps(layout(), filesystem="ntfs")
        self.assertEqual(caught.exception.code, "filesystem.unsupported")

    def test_only_fixed_mount_target_is_accepted(self) -> None:
        for target in ("/", "/tmp", "/mnt2", "/mnt/../root", "/mnt/../../etc", "//mnt", "/mnt\\n"):
            with self.subTest(target=target), self.assertRaises(Refused) as caught:
                plan_steps(layout(), target=target)
            self.assertEqual(caught.exception.code, "target.fixed")
        self.assertTrue(plan_steps(layout(), target=TARGET_MOUNTPOINT))

    def test_layout_retains_disk_size_and_named_consent(self) -> None:
        proposed = layout()
        self.assertEqual(proposed.disk_size_bytes, 256 * GIB)
        self.assertEqual(proposed.acknowledgement, "/dev/nvme0n1")

    def test_mutated_partition_plan_is_refused(self) -> None:
        proposed = layout()
        proposed.partitions[0]["name"] = "wsm-other"
        with self.assertRaises(Refused) as caught:
            plan_steps(proposed)
        self.assertEqual(caught.exception.code, "layout.partition-plan")

    def test_firmware_specific_minimum_size_is_rechecked_in_step_planner(self) -> None:
        for firmware in ("uefi", "bios"):
            with self.subTest(firmware=firmware):
                proposed = layout(firmware, "/dev/nvme0n1")
                proposed.disk_size_bytes = minimum_disk_size_bytes(firmware)
                self.assertTrue(plan_steps(proposed))
                proposed.disk_size_bytes -= 1
                with self.assertRaises(Refused) as caught:
                    plan_steps(proposed)
                self.assertEqual(caught.exception.code, "disk.too-small")

    def test_backend_command_rechecks_minimum_disk_geometry(self) -> None:
        for firmware in ("uefi", "bios"):
            with self.subTest(firmware=firmware):
                proposed = layout(firmware, "/dev/nvme0n1")
                proposed.disk_size_bytes = 1
                with self.assertRaises(Refused) as caught:
                    backend_command(proposed)
                self.assertEqual(caught.exception.code, "disk.too-small")

    def test_missing_disk_size_is_refused(self) -> None:
        proposed = layout()
        proposed.disk_size_bytes = None
        with self.assertRaises(Refused) as caught:
            plan_steps(proposed)
        self.assertEqual(caught.exception.code, "disk.size-unrecorded")

    def test_lost_disk_acknowledgement_is_refused_before_planning(self) -> None:
        proposed = layout()
        proposed.acknowledgement = None
        with self.assertRaises(Refused) as caught:
            plan_steps(proposed)
        self.assertEqual(caught.exception.code, "disk.acknowledgement")


class BackendCommandTests(unittest.TestCase):
    def test_command_shape(self) -> None:
        command = backend_command(layout())
        self.assertEqual(
            command,
            [
                "/run/current-system/profile/bin/guix", "time-machine", "-C", CHANNEL_LOCK_PATH, "--",
                "system", "init", SYSTEM_CONFIG_PATH, TARGET_MOUNTPOINT,
            ],
        )

    def test_arbitrary_system_file_is_refused(self) -> None:
        for path in ("systems/desktop.scm", "../../other.scm", "/tmp/other.scm", "/run/wsm/other.scm"):
            with self.subTest(path=path), self.assertRaises(Refused):
                backend_command(layout(), system_file=path)

    def test_arbitrary_backend_target_is_refused(self) -> None:
        for target in ("/", "/tmp", "/mnt2", "/mnt/../root", "//mnt"):
            with self.subTest(target=target), self.assertRaises(Refused):
                backend_command(layout(), target=target)

    def test_backend_handoff_requires_disk_acknowledgement_and_size(self) -> None:
        proposed = layout()
        proposed.acknowledgement = None
        with self.assertRaises(Refused) as caught:
            backend_command(proposed)
        self.assertEqual(caught.exception.code, "disk.acknowledgement")

        proposed = layout()
        proposed.disk_size_bytes = None
        with self.assertRaises(Refused) as caught:
            backend_command(proposed)
        self.assertEqual(caught.exception.code, "disk.size-unrecorded")


class RenderTests(unittest.TestCase):
    def test_documented_command_example_uses_only_allowlisted_guix_profile_paths(self) -> None:
        document = (ROOT / "docs" / "INSTALL-SEQUENCE.md").read_text(encoding="utf-8")
        match = re.search(r"```sh\n(.*?)\n```", document, flags=re.DOTALL)
        self.assertIsNotNone(match)
        commands = [
            line.split()[0]
            for line in match.group(1).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        allowed = set(TRUSTED_TOOLS.values()) | {"/run/current-system/profile/bin/guix"}
        self.assertTrue(commands)
        self.assertTrue(set(commands).issubset(allowed), set(commands) - allowed)
        self.assertFalse(any("/usr/" in line for line in match.group(1).splitlines()))

    def test_render_warns_and_marks_destructive_steps(self) -> None:
        text = render(plan_steps(layout()), backend_command(layout()))
        self.assertIn("NOT EXECUTED", text)
        self.assertIn("DESTRUCTIVE", text)
        self.assertIn("guix time-machine", text)
        self.assertIn(CHANNEL_LOCK_PATH, text)
        self.assertIn(SYSTEM_CONFIG_PATH, text)


if __name__ == "__main__":
    unittest.main()
