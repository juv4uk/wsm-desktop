# Disposable QEMU installer harness — first increment

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Status: **harness plus synthetic-ISO integration; WSM image integration pending**
- Related: #1 (Guix VM milestone), #13 (read-only CLI), #14 (QEMU integration), #23 (session freshness)
- Script: `scripts/qemu_boot_smoke.py`

## What this increment proves

The script provides a guarded QEMU boot-smoke runner for a user-supplied live ISO. It creates a new qcow2 disk inside a temporary directory, boots with software emulation, disables networking, captures serial output, and optionally confirms a caller-supplied boot marker.

The repository CI now builds a small synthetic bootable ISO and boots it through this actual harness, requiring a guest-only serial marker. This exercises the harness end-to-end against a disposable guest, but it is **not** a WSM Guix image and does **not** yet run `wsm-install` inside the guest. That final step still requires the reproducible Guix/WSM artifact from #1 and an agreed guest-side invocation channel.

## Safety model

- The only writable virtual disk is a newly created qcow2 file inside an automatically cleaned temporary directory.
- The ISO is attached as a CD-ROM source.
- No host block device, physical disk, USB passthrough, GPU passthrough, shared host folder, or host EFI variable store is attached.
- QEMU uses TCG software emulation and no network interface.
- No firmware update, package installation, bootloader write, or host mount is performed.
- The script never invokes Guix, Nix, or the installer backend.

## Usage

Install QEMU's `qemu-system-x86_64` and `qemu-img` in the disposable test environment, then:

```sh
python3 scripts/qemu_boot_smoke.py --iso /path/to/wsm-live.iso \
  --timeout-seconds 120 --boot-marker 'WSM-LIVE-READY'
```

Inspect the captured serial output in the JSON result. A boot is reported as confirmed only when the exact configured marker appears. A QEMU process timeout is expected for a live system that remains running; it is not itself a failure if the marker was observed.

To inspect the generated command without launching QEMU:

```sh
python3 scripts/qemu_boot_smoke.py --iso /path/to/wsm-live.iso --dry-run
```

## Exit codes

- `0` — configured serial boot marker observed, or command-only dry-run completed.
- `2` — invalid input or required QEMU binaries missing.
- `3` — QEMU disk creation or process launch failure.
- `4` — boot was not confirmed (missing marker or marker not observed).

## Integration evidence and remaining work

The `qemu-harness-integration` job in `.github/workflows/checks.yml` creates a synthetic ISO in the runner's temporary directory, launches the project harness with a fresh qcow2, and requires `WSM_QEMU_HARNESS_ISO_BOOT_OK` from the guest serial console. It also runs the harness's real-QEMU CLI parsing regression. It does not use a host disk, host device passthrough, network, shared folders, or EFI variable store.

Remaining acceptance work for #14:

1. Obtain a verified Guix channel snapshot and build the actual minimal Guix/WSM guest artifact from it.
2. Boot that artifact through this harness, not merely the generic synthetic ISO.
3. Add a guest-side invocation mechanism for `wsm-install --preflight ... --dry-run` without host-folder or device passthrough.
4. Verify the guest plan JSON reports `backend_invoked=false`, `disk_access_performed=false`, and `plan_confirmable=false`.
5. Add a reboot/session-change test once the freshness contract in #23 and producer fields in #5/#6 are ratified.

A passing unit test or QEMU command construction test is not a VM boot. A boot marker is not proof that the installer CLI ran inside the guest.
