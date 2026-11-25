# SPDX-License-Identifier: LicenseRef-Volnist
"""The partition planner must refuse far more often than it agrees."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wsm_install.partition import (  # noqa: E402
    BIOS_BOOT_MIB,
    ESP_MIB,
    Disk,
    Refused,
    plan,
    render,
)

GIB = 1024 ** 3


def disk(**overrides) -> Disk:
    base = {
        "path": "/dev/nvme0n1",
        "size_bytes": 256 * GIB,
        "is_removable": False,
        "holds_running_system": False,
        "has_existing_data": True,
    }
    base.update(overrides)
    return Disk(**base)


class LayoutTests(unittest.TestCase):
    def test_uefi_layout_is_esp_then_root(self) -> None:
        layout = plan(disk(), "uefi", acknowledgement="/dev/nvme0n1")
        roles = [part["role"] for part in layout.partitions]
        self.assertEqual(roles, ["esp", "root"])
        self.assertEqual(layout.partitions[0]["end"], f"{1 + ESP_MIB}MiB")

    def test_bios_layout_has_a_bios_grub_partition(self) -> None:
        layout = plan(disk(), "bios", acknowledgement="/dev/nvme0n1")
        self.assertEqual(layout.partitions[0]["typecode"], "ef02")
        self.assertEqual(layout.partitions[0]["end"], f"{1 + BIOS_BOOT_MIB}MiB")

    def test_root_partition_takes_the_rest(self) -> None:
        layout = plan(disk(), "uefi", acknowledgement="/dev/nvme0n1")
        self.assertEqual(layout.partitions[-1]["end"], "0")

    def test_no_swap_partition_is_planned(self) -> None:
        """zram is the swap strategy; a swap partition on SSD is the opposite."""
        layout = plan(disk(), "uefi", acknowledgement="/dev/nvme0n1")
        self.assertNotIn("swap", {part["role"] for part in layout.partitions})

    def test_commands_start_with_zap_all(self) -> None:
        layout = plan(disk(), "uefi", acknowledgement="/dev/nvme0n1")
        self.assertEqual(layout.commands()[0], ["sgdisk", "--zap-all", "/dev/nvme0n1"])

    def test_render_says_it_is_not_executed(self) -> None:
        text = render(plan(disk(), "uefi", acknowledgement="/dev/nvme0n1"))
        self.assertIn("NOT EXECUTED", text)
        self.assertIn("sgdisk", text)


class RefusalTests(unittest.TestCase):
    def assertRefused(self, code: str, **kwargs) -> None:
        with self.assertRaises(Refused) as caught:
            plan(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_partition_path_is_refused(self) -> None:
        self.assertRefused(
            "disk.path",
            disk=disk(path="/dev/nvme0n1p1"),
            firmware="uefi",
            acknowledgement="/dev/nvme0n1p1",
        )

    def test_disk_image_is_refused(self) -> None:
        self.assertRefused(
            "disk.path", disk=disk(path="/tmp/disk.img"), firmware="uefi",
            acknowledgement="/tmp/disk.img",
        )

    def test_running_system_disk_is_refused(self) -> None:
        self.assertRefused(
            "disk.running-system", disk=disk(holds_running_system=True),
            firmware="uefi", acknowledgement="/dev/nvme0n1",
        )

    def test_too_small_disk_is_refused(self) -> None:
        self.assertRefused(
            "disk.too-small", disk=disk(size_bytes=4 * GIB),
            firmware="uefi", acknowledgement="/dev/nvme0n1",
        )

    def test_wiping_without_acknowledgement_is_refused(self) -> None:
        self.assertRefused("disk.acknowledgement", disk=disk(), firmware="uefi")

    def test_boolean_acknowledgement_is_not_enough(self) -> None:
        """The acknowledgement must name the disk, not say 'yes'."""
        self.assertRefused(
            "disk.acknowledgement", disk=disk(), firmware="uefi", acknowledgement="yes"
        )

    def test_acknowledgement_for_another_disk_is_refused(self) -> None:
        self.assertRefused(
            "disk.acknowledgement", disk=disk(), firmware="uefi",
            acknowledgement="/dev/sda",
        )

    def test_size_drift_is_refused(self) -> None:
        self.assertRefused(
            "disk.size-drift", disk=disk(), firmware="uefi",
            acknowledgement="/dev/nvme0n1", expected_size_bytes=64 * GIB,
        )

    def test_unknown_firmware_is_refused(self) -> None:
        self.assertRefused(
            "disk.firmware", disk=disk(), firmware="coreboot",
            acknowledgement="/dev/nvme0n1",
        )

    def test_empty_disk_still_requires_acknowledgement_for_partition_table_replacement(self) -> None:
        self.assertRefused(
            "disk.acknowledgement",
            disk=disk(has_existing_data=False),
            firmware="uefi",
        )
        layout = plan(
            disk(has_existing_data=False),
            "uefi",
            acknowledgement="/dev/nvme0n1",
        )
        self.assertEqual(layout.partitions[0]["role"], "esp")


if __name__ == "__main__":
    unittest.main()
