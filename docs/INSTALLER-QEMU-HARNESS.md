# Disposable QEMU installer harness

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Status: **QEMU harness and synthetic-ISO CI integration available; Guix/WSM guest acceptance pending**
- Related: #1 (Guix VM milestone), #13 (read-only CLI), #14 (QEMU integration), #23 (session freshness), #27 (harness)
- Harness: `scripts/qemu_boot_smoke.py`
- Synthetic-ISO integration: `.github/workflows/qemu-harness-iso-integration.yml`
- Generic Linux guest smoke: `scripts/ci_qemu_guest_smoke.sh`

## What is implemented

The project harness accepts a user-supplied regular ISO, validates bounded disk/RAM/CPU/time parameters, creates a new qcow2 in a temporary directory, runs QEMU with TCG and no network, captures serial output, and optionally requires an exact caller-supplied boot marker. QEMU block-device arguments use structured JSON nodes; the harness does not attach host block devices or pass through USB/GPU devices or EFI variables.

The dedicated synthetic-ISO CI workflow builds a tiny disposable GRUB/BusyBox guest, passes it through the actual project harness, and requires the guest-only marker `WSM_QEMU_HARNESS_ISO_BOOT_OK`. A separate `qemu-guest-smoke` job in `.github/workflows/checks.yml` directly boots the GitHub runner kernel with a minimal BusyBox initramfs and checks `WSM_QEMU_GUEST_INIT_OK`. These tests cover different layers: direct guest-kernel execution and the project's ISO/QEMU harness.

## Output capture bounds

Serial and stderr output are drained concurrently while QEMU runs. The harness retains at most 1 MiB of serial data and 256 KiB of stderr as rolling tails, while scanning the complete serial stream for the configured boot marker, including matches that cross read-chunk boundaries. The JSON reports total byte counts plus `serial_output_truncated` / `qemu_error_truncated` flags; the display field `serial_output_tail` is limited to the final 4,000 characters. Boot markers are limited to 4 KiB of UTF-8 data.

## What a pass means — and does not mean

The direct guest smoke proves that a generic Linux kernel and init process can execute under QEMU TCG. The synthetic-ISO integration proves that the project harness can create its disposable disk, launch QEMU, capture serial output, and observe a marker from a controlled guest.

Neither test boots a Guix-generated WSM system image. Neither runs `wsm-install` inside a WSM guest. Neither validates the host's physical GPU, Wi-Fi, audio, display, storage, or firmware. They must not be presented as WSM ISO, installer, or physical-hardware compatibility evidence.

## Isolation

- Only GitHub-hosted runners and QEMU TCG are used.
- Guest networking is disabled.
- Writable qcow2 images and generated ISO/initramfs files live only in temporary runner directories and are deleted after the run.
- No host disks, host block devices, USB/GPU passthrough, shared host folders, EFI variable store, or physical hardware access is used.
- No Guix/Nix backend, firmware updater, or installer apply operation is invoked.
- Workflows use `contents: read` and no repository secrets.

## Next acceptance steps

1. Obtain the verified, authenticated Guix channel lock from #39; do not substitute a moving channel snapshot.
2. Build the minimal Guix/WSM guest artifact from that exact snapshot in a bounded disposable runner.
3. Boot that artifact through `scripts/qemu_boot_smoke.py` and capture the guest marker/log.
4. Execute `wsm-install --preflight ... --dry-run` inside the guest without host-folder or host-device passthrough.
5. Assert the guest plan reports `dry_run=true`, `backend_invoked=false`, `disk_access_performed=false`, and `plan_confirmable=false`.

A generic guest boot or synthetic ISO marker is not a substitute for these steps.