# Guix System configurations

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

The minimal.scm file is a bring-up example intended for syntax/build testing and disposable virtual machines. It is not a release profile, not a live image, and not a production installer target.

Before deploying to a target:
- verify all filesystem identifiers;
- verify EFI System Partition mount and bootloader target;
- define regular user accounts through the generated configuration;
- choose and test the desktop environment and services;
- inspect the complete configuration;
- test the exact configuration in QEMU.

Do not run guix system init against a physical disk as a substitute for these tests.
