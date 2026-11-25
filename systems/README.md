# Guix System configurations

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

The minimal.scm file is a bring-up example intended for syntax/build testing and disposable virtual machines. It is not a release profile, not a live image, and not a production installer target.

## VM boot modes and the selected bootloader

On GNU/Linux, \`guix system vm CONFIG.scm\` defaults to direct-kernel boot. That default path does **not** exercise the bootloader declared in the operating-system configuration.

To test a complete boot sequence starting at the bootloader, use \`guix system vm --full-boot CONFIG.scm\`. This configuration selects BIOS GRUB (\`grub-bootloader\`) with \`/dev/vda\` as its target for the disposable BIOS/SeaBIOS full-boot VM profile. This is a profile choice for that boot path; it is **not** a claim that every \`guix system vm\` invocation creates an MBR image or exercises GRUB.

\`guix system image --image-type=qcow2 CONFIG.scm\` is a separate image-generation action, not another spelling of the default \`vm\` path. Check the image-type and bootloader behavior against the manual for the exact Guix revision selected by the channel snapshot; do not infer it from the default \`vm\` behavior.

The BIOS GRUB selection addresses the observed EFI/GPT incompatibility in the tested full-boot VM configuration. It is not by itself proof that the post-change system builds or boots. The exact post-fix \`guix system build\`, \`guix system vm --full-boot\`, and disposable QEMU guest boot still need to be recorded against a reviewed channel snapshot (see #1 and #39). Until those results are attached, treat this file as a VM-oriented configuration correction, not a boot-tested system.

Before deploying to a target:
- verify all filesystem identifiers;
- for a UEFI target, replace \`grub-bootloader\` with \`grub-efi-bootloader\`, mount an EFI System Partition at \`/boot/efi\`, and use a GPT image or real target disk;
- verify the bootloader target;
- define regular user accounts through the generated configuration;
- choose and test the desktop environment and services;
- inspect the complete configuration;
- test the exact configuration in QEMU.

Do not run guix system init against a physical disk as a substitute for these tests.
