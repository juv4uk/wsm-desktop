# Guix System configurations

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

The minimal.scm file is a bring-up example intended for syntax/build testing and disposable virtual machines. It is not a release profile, not a live image, and not a production installer target.

It uses BIOS Grub on `/dev/vda` because `guix system vm` builds an MBR disk image and rejects an EFI bootloader for that image type. An EFI bootloader requires a GPT image, which the `vm` action does not produce.

This pairing addresses the observed `grub-efi`/GPT incompatibility in the VM image path; it is not by itself proof that the post-change system boots. The exact post-fix `guix system build`, `guix system vm`, and disposable QEMU guest boot still need to be recorded against a reviewed channel snapshot (see #1 and #39). Until those results are attached, treat this file as a VM-oriented configuration correction, not a boot-tested system.

Before deploying to a target:
- verify all filesystem identifiers;
- for a UEFI target, replace `grub-bootloader` with `grub-efi-bootloader`, mount an EFI System Partition at `/boot/efi`, and use a GPT image or real target disk;
- verify the bootloader target;
- define regular user accounts through the generated configuration;
- choose and test the desktop environment and services;
- inspect the complete configuration;
- test the exact configuration in QEMU.

Do not run guix system init against a physical disk as a substitute for these tests.
