# Guix System configurations

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

The minimal.scm file is a bring-up example intended for syntax/build testing and disposable virtual machines. It is not a release profile, not a live image, and not a production installer target.

It uses BIOS Grub on `/dev/vda` because `guix system vm` builds an MBR disk image and rejects an EFI bootloader for that image type. An EFI bootloader requires a GPT image, which the `vm` action does not produce.

Before deploying to a target:
- verify all filesystem identifiers;
- for a UEFI target, replace `grub-bootloader` with `grub-efi-bootloader`, mount an EFI System Partition at `/boot/efi`, and use a GPT image or real target disk;
- verify the bootloader target;
- define regular user accounts through the generated configuration;
- choose and test the desktop environment and services;
- inspect the complete configuration;
- test the exact configuration in QEMU.

Do not run guix system init against a physical disk as a substitute for these tests.
