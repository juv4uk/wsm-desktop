# Real QEMU guest boot in GitHub Actions

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

**Status:** CI experiment. This is a generic Linux guest boot smoke test, not a WSM installer image test.

Workflow job: `qemu-guest-smoke` in `.github/workflows/checks.yml`  
Runner script: `scripts/ci_qemu_guest_smoke.sh`

## What the experiment proves

The GitHub-hosted Ubuntu runner supplies a Linux kernel. The workflow builds a tiny initramfs containing static BusyBox and a minimal `/init`, then boots that kernel as a guest under QEMU's TCG software emulator. The guest must print `WSM_QEMU_GUEST_INIT_OK` on its serial console and power off within a 45-second timeout.

Unlike command-construction unit tests, this executes a real guest kernel and guest init process.

## Isolation boundary

- QEMU uses TCG; no KVM or host CPU passthrough is requested.
- No network interface is created (`-nic none`).
- No virtual disk, host block device, USB/GPU passthrough, shared folder, or EFI variable store is attached.
- The guest initramfs is built in a temporary runner directory and deleted after the test.
- The workflow has `contents: read`, uses no repository secrets, and has a ten-minute job timeout.

## What it does not prove

This test does not boot a WSM ISO, evaluate a Guix/Nix system definition, execute `wsm-install` in a WSM guest, or validate physical hardware. Those require a reproducible WSM image artifact and a separate guest-side acceptance path. A passing generic guest boot must never be reported as WSM hardware compatibility.

## Failure behavior

The job fails if the runner kernel or required tools are unavailable, initramfs creation fails, the serial marker is absent, or QEMU does not exit successfully before timeout. On failure, the script prints only the bounded serial-log tail; it does not publish host inventory or hardware identifiers.
