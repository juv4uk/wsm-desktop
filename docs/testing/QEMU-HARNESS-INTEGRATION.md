# Integration test for the WSM QEMU boot harness

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Status: **CI experiment**
- Related: #14 (QEMU integration), #27 (QEMU harness), #35/#38 (resource and path hardening), #34 (generic guest boot)
- Workflow: `.github/workflows/qemu-harness-iso-integration.yml`

## Purpose

The generic guest-boot experiment in #34 proves that QEMU TCG can execute a Linux kernel and a minimal `/init`. This experiment goes one step further: it builds a tiny bootable ISO inside the GitHub-hosted runner and sends that ISO through the actual `scripts/qemu_boot_smoke.py` program.

It therefore exercises the project harness's input validation, disposable qcow2 creation, QEMU command construction, serial capture, marker detection, and JSON result contract.

## Test construction

The workflow uses the runner's existing kernel image, static BusyBox, a minimal initramfs, GRUB and xorriso. The guest `/init` prints the unique marker `WSM_QEMU_HARNESS_ISO_BOOT_OK` to its serial console and powers off. The harness is invoked with a 256 MiB disposable qcow2, 512 MiB guest memory, one vCPU, and a 45-second process timeout.

The ISO and initramfs are generated locally in the temporary GitHub runner workspace; no external ISO or kernel download is required.

## Isolation boundary

- GitHub-hosted Ubuntu runner and QEMU TCG software emulation only.
- No network device, KVM, host CPU passthrough, host block device, USB/GPU passthrough, shared folder, or EFI variable store is attached.
- The only writable guest disk is the newly-created qcow2 file in the harness's temporary directory.
- The runner kernel image is copied read-only as an input to the synthetic ISO; the host kernel is not installed, replaced, or modified.
- Workflow token permission is `contents: read`; no repository secrets are used.
- The test does not run Guix, Nix, `wsm-install`, or any installation backend.

## What a pass means

A pass means the generated ISO booted under QEMU through the actual project harness, the guest's init process emitted the expected marker, and the harness returned a JSON result with the expected isolation flags.

It does **not** prove that a WSM ISO boots, that a Guix/Nix system builds, that `wsm-install` runs inside a WSM guest, or that any physical computer is compatible. Those require separate artifacts and tests.

## Failure behavior

The workflow fails if it cannot find the runner kernel, build the initramfs/ISO, create the disposable qcow2, launch QEMU, observe the guest marker, or validate the harness result. The harness itself enforces the configured disk, memory, CPU, and timeout limits.
