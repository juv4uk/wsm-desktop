# WSM hardware preflight collector

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Status: **prototype v0.2.0** — read-only evidence collector, not a hardware certification, compatibility score, or end-to-end function test.
- Critical path: **yes** — the installer consumes this report before it writes to a disk.

## Run

From the repository root:

    python3 -m wsm_hwcheck
    python3 -m wsm_hwcheck --output ./hardware-report.json

The output file is written only when the user explicitly provides --output. With no output path the JSON report is printed to stdout.

The inventory collector reads Linux sysfs under /sys and procfs under /proc (or test roots supplied through hidden test-only CLI options). Runtime diagnostics additionally read the local /lib/modules/<kernel-release>/modules.alias, modules.dep and modules.builtin indexes, plus the current-boot kernel log through journalctl or dmesg.

The inventory layer reads local sysfs/procfs. Optional runtime diagnostics may invoke fixed, read-only journalctl or dmesg commands for current-boot kernel messages. The collector does not load or unload modules, install packages, access the network, update firmware, write target disks, alter UEFI variables, or change bootloader state.

## Inventory layer (v0.1)

- CPU model/vendor fields exposed through /proc/cpuinfo.
- DMI platform and motherboard model fields, excluding serial-number files.
- PCI identifiers, modaliases and PCI-function driver binding.
- USB parent-device identifiers only; composite USB interface classes and per-interface driver bindings are not collected in v0.1.
- Block storage model/vendor and kernel driver binding when exposed through sysfs.
- DRM connector connection state and kernel-exposed modes when available; EDID monitor identification and explicit connector-to-GPU relationships are not collected in v0.1.

## Runtime driver and firmware evidence (v0.2)

- Match PCI/USB modaliases against the running kernel's local /lib/modules/<kernel-release>/modules.alias file, then corroborate candidate names against modules.dep plus the resolved module file on disk, or against modules.builtin. A matching alias without a corroborating module artifact is not treated as an available driver when both indexes are complete.
- Observe loaded module names under /sys/module and preserve the distinction between a candidate available in the current kernel tree, a loaded-but-unbound module, and a sysfs-bound driver. If module indexes are incomplete, availability remains uncertain rather than being marked unsupported.
- Inspect the current boot's kernel log using fixed journalctl arguments, with dmesg as a fallback. Output is streamed through a 2 MiB tail buffer, stderr is capped, and each process has a hard timeout; truncation is reported.
- A direct-loading debug message maps to available-not-confirmed-loaded: it shows that the blob was read into the firmware request buffer. A driver-reported loaded firmware version also maps to available-not-confirmed-loaded because it does not prove device acceptance or initialization. This prototype deliberately does not emit loaded from these generic signatures; reserve that state for a reviewed, device-specific positive signal.
- Store normalized summaries, not raw kernel-log lines. Missing log access or no attributable event leaves firmware state unknown.

## Known v0.1 coverage gaps

- USB composite-device functions are not enumerated as separate `*:1.N` interface records. A parent `bDeviceClass` value of `00` stays `other`; no interface-level driver binding is claimed. See #18 for the separately versioned topology work.
- DRM connector records are not physical-monitor identities. v0.1 does not decode EDID or link a connector to its owning GPU; those relationships remain unknown until explicit topology evidence is implemented.
- An observed connector state or active mode is inventory/runtime evidence only. It is never emitted as a passed functional test.

## What it does not yet prove

- Whether a network interface can associate with an access point or reach the Internet.
- Whether a GPU can sustain a requested display mode or accelerate a desktop session.
- Whether audio output/input, Bluetooth, webcam, suspend/resume or power management work end-to-end.
- Whether a device requires a particular runtime firmware blob when no attributable current-boot kernel message was observed.
- Whether an external report for a similar model matches the current board revision and kernel.

These remain unknown or not-tested. A bound driver is not presented as a successful function test.

Linux's firmware-loader implementation emits a generic `direct-loading` debug
message before the firmware request is finally assigned to the device; WSM therefore
does not classify that message as a successful load. See the
[upstream firmware loader](https://github.com/torvalds/linux/blob/master/drivers/base/firmware_loader/main.c)
and [request_firmware API documentation](https://www.kernel.org/doc/html/latest/driver-api/firmware/request_firmware.html).

## Report and privacy

The report follows [WSM Hardware Evidence Report v1](REPORT-FORMAT.md). It uses a random per-run report ID and omits serial numbers, MAC addresses, UUIDs, hostnames, usernames, IP addresses and storage WWNs. v1 makes no network requests and performs no uploads. Runtime kernel logs are parsed locally; only normalized, device-attributed summaries are included, never raw log lines.

The Python implementation has no third-party Python runtime dependency. Runtime kernel-log diagnostics opportunistically use the host's existing journalctl or dmesg command; when neither is available/readable, the report records that fact and preserves unknown states. Upstream tools such as hwinfo, hw-probe, LKDDb-backed references, edid-decode and libdisplay-info remain optional evidence providers pending package, privacy, licensing and runtime review.
