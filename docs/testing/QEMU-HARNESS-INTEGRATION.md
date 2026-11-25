# Disposable synthetic-ISO integration test for the WSM QEMU harness

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Status: **CI integration experiment**
- Related: #14 (QEMU installer integration), #27 (QEMU harness), #34 (generic QEMU guest boot), #35/#38 (harness hardening)
- Workflow job: `qemu-harness-integration` in `.github/workflows/checks.yml`
- Runner: `scripts/ci_qemu_harness_iso_integration.sh`

## What it proves

The workflow builds a minimal, disposable bootable ISO using the GitHub runner's existing Linux kernel, static BusyBox, an initramfs, GRUB and xorriso. It then invokes the actual `scripts/qemu_boot_smoke.py` program with a fresh temporary qcow2 disk and requires the guest-only serial marker `WSM_QEMU_HARNESS_ISO_BOOT_OK`.

This is stronger than a mocked command test: the project harness validates its inputs, creates a disposable qcow2, launches QEMU under TCG, captures the serial console, and observes the marker emitted by the guest's `/init`.

## Isolation

- The ISO tree and qcow2 are created under a runner temporary directory and removed after the job.
- QEMU uses TCG and has no guest network interface.
- No host block devices, USB/GPU passthrough, host folders, or EFI variable store are attached.
- The guest receives only the synthetic kernel/initramfs ISO and a newly created disposable qcow2.
- The workflow uses `contents: read`, no repository secrets, and a bounded job timeout.
- The test does not run `wsm-install`, invoke Guix/Nix, or write to physical hardware.

## What it does not prove

The synthetic ISO is a harness test fixture, not a WSM live image and not the output of `guix system vm`. A successful marker proves only that the harness boots a controlled guest and receives its serial output. It does not establish support for the user's GPU, network, audio, monitor, firmware, or any other physical device.

The actual #14 acceptance target remains: boot a verified Guix/WSM artifact and execute `wsm-install --dry-run` inside that guest, while preserving all read-only and no-host-device guarantees.
