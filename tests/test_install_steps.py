# SPDX-License-Identifier: LicenseRef-Volnist
"""The install-step planner is ordered, explicit, and never executes commands."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.install_steps import (  # noqa: E402
    CHANNEL_LOCK_PATH,
    SYSTEM_CONFIG_PATH,
    TARGET_MOUNTPOINT,
    backend_command,
    device_for,
    plan_steps,
    render,
)
from wsm_install.partition import Disk, Refused, plan  # noqa: E402

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

    def test_partition_number_must_be_positive_integer(self) -> None:
        for number in (0, -1, True, "2"):
            with self.subTest(number=number), self.assertRaises(Refused):
                device_for("/dev/sda", number)

    def test_disk_path_must_be_a_whole_allowlisted_device(self) -> None:
        for path in ("/dev/nvme0n1p1", "/dev/sda1", "/tmp/disk.img", "/dev/../sda"):
            with self.subTest(path=path), self.assertRaises(Refused):
                device_for(path, 1)


class OrderingTests(unittest.TestCase):
    def test_partition_table_is_created_before_partprobe_and_formatting(self) -> None:
        steps = plan_steps(layout())
        commands = [step.command for step in steps]
        sgdisk = [step for step in steps if step.command[0] == "sgdisk"]
        self.assertEqual(len(sgdisk), 3)
        self.assertEqual(sgdisk[0].command, ["sgdisk", "--zap-all", "/dev/nvme0n1"])
        self.assertTrue(all(step.destructive for step in sgdisk))
        partprobe_index = next(i for i, command in enumerate(commands) if command[0] == "partprobe")
        mkfs_index = next(i for i, command in enumerate(commands) if command[0] == "mkfs.ext4")
        self.assertLess(max(i for i, command in enumerate(commands) if command[0] == "sgdisk"), partprobe_index)
        self.assertLess(partprobe_index, mkfs_index)

    def test_root_is_mounted_before_the_esp(self) -> None:
        steps = plan_steps(layout())
        mounts = [step.command for step in steps if step.command[0] == "mount"]
        self.assertEqual(mounts[0], ["mount", "/dev/nvme0n1p2", TARGET_MOUNTPOINT])
        self.assertEqual(mounts[1], ["mount", "/dev/nvme0n1p1", f"{TARGET_MOUNTPOINT}/boot/efi"])

    def test_all_mount_targets_are_inside_the_fixed_target(self) -> None:
        steps = plan_steps(layout())
        targets = [step.command[-1] for step in steps if step.command[0] == "mount"]
        self.assertTrue(all(target == TARGET_MOUNTPOINT or target.startswith(TARGET_MOUNTPOINT + "/") for target in targets))

    def test_uefi_formats_a_fat32_esp(self) -> None:
        steps = plan_steps(layout("uefi"))
        fat = [step for step in steps if step.command[0] == "mkfs.fat"]
        self.assertEqual(len(fat), 1)
        self.assertIn("32", fat[0].command)

    def test_bios_has_no_esp_step(self) -> None:
        steps = plan_steps(layout("bios", "/dev/sda"))
        self.assertFalse(any(step.command[0] == "mkfs.fat" for step in steps))
        self.assertTrue(any("--typecode=1:ef02" in step.command for step in steps if step.command[0] == "sgdisk"))

    def test_partition_table_and_format_steps_are_destructive(self) -> None:
        steps = plan_steps(layout())
        destructive = [step.command[0] for step in steps if step.destructive]
        self.assertEqual(destructive.count("sgdisk"), 3)
        self.assertIn("mkfs.ext4", destructive)
        self.assertIn("mkfs.fat", destructive)

    def test_mounting_is_not_marked_destructive(self) -> None:
        steps = plan_steps(layout())
        for step in steps:
            if step.command[0] == "mount":
                self.assertFalse(step.destructive)

    def test_layout_retains_disk_size_and_exact_acknowledgement(self) -> None:
        proposed = layout()
        self.assertEqual(proposed.disk_size_bytes, 256 * GIB)
        self.assertEqual(proposed.acknowledgement, "/dev/nvme0n1")

    def test_missing_observed_disk_size_is_refused(self) -> None:
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


class FilesystemChoiceTests(unittest.TestCase):
    def test_btrfs_is_available_and_uses_force(self) -> None:
        steps = plan_steps(layout(), filesystem="btrfs")
        mkfs = [step for step in steps if step.command[0] == "mkfs.btrfs"]
        self.assertEqual(len(mkfs), 1)
        self.assertIn("-f", mkfs[0].command)

    def test_unknown_filesystem_is_refused(self) -> None:
        with self.assertRaises(Refused) as caught:
            plan_steps(layout(), filesystem="ntfs")
        self.assertEqual(caught.exception.code, "filesystem.unsupported")

    def test_only_the_fixed_mount_target_is_accepted(self) -> None:
        for unsafe in (
            "/",
            "/tmp",
            "/mnt2",
            "/mnt/../root",
            "/mnt/../../etc",
            "//mnt",
            "/mnt\n",
        ):
            with self.subTest(target=unsafe), self.assertRaises(Refused) as caught:
                plan_steps(layout(), target=unsafe)
            self.assertEqual(caught.exception.code, "target.fixed")

        self.assertTrue(plan_steps(layout(), target=TARGET_MOUNTPOINT))


class BackendCommandTests(unittest.TestCase):
    def test_command_uses_fixed_paths_and_the_authenticated_channel_lock(self) -> None:
        command = backend_command(layout())
        self.assertEqual(
            command,
            [
                "guix",
                "time-machine",
                "-C",
                CHANNEL_LOCK_PATH,
                "--",
                "system",
                "init",
                SYSTEM_CONFIG_PATH,
                TARGET_MOUNTPOINT,
            ],
        )

    def test_arbitrary_scheme_file_is_refused(self) -> None:
        for path in ("systems/desktop.scm", "../../other.scm", "/tmp/other.scm", "/run/wsm/other.scm"):
            with self.subTest(path=path), self.assertRaises(Refused) as caught:
                backend_command(layout(), system_file=path)
            self.assertEqual(caught.exception.code, "backend.system-file")

    def test_arbitrary_backend_target_is_refused(self) -> None:
        for target in ("/", "/tmp", "/mnt2", "/mnt/../root", "//mnt"):
            with self.subTest(target=target), self.assertRaises(Refused) as caught:
                backend_command(layout(), target=target)
            self.assertEqual(caught.exception.code, "target.fixed")

    def test_backend_handoff_also_requires_carried_disk_acknowledgement(self) -> None:
        proposed = layout()
        proposed.acknowledgement = None
        with self.assertRaises(Refused) as caught:
            backend_command(proposed)
        self.assertEqual(caught.exception.code, "disk.acknowledgement")


class RenderTests(unittest.TestCase):
    def test_render_warns_and_marks_all_destructive_steps(self) -> None:
        text = render(plan_steps(layout()), backend_command(layout()))
        self.assertIn("NOT EXECUTED", text)
        self.assertIn("DESTRUCTIVE", text)
        self.assertIn("sgdisk --zap-all", text)
        self.assertIn("guix time-machine", text)
        self.assertIn(CHANNEL_LOCK_PATH, text)
        self.assertIn(SYSTEM_CONFIG_PATH, text)


if __name__ == "__main__":
    unittest.main()
