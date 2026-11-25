# WSM hardware preflight collector

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Status: **prototype v0.1.0**. This is a read-only inventory collector, not a compatibility certification tool.

## Run

From the repository root:

    python3 -m wsm_hwcheck
    python3 -m wsm_hwcheck --output ./hardware-report.json

The output file is written only when the user explicitly provides --output. With no output path the JSON report is printed to stdout.

The collector reads only:
- Linux sysfs under /sys (or a test root supplied with --sysfs-root);
- Linux procfs under /proc (or a test root supplied with --proc-root).

It does not run subprocesses, access the network, load kernel modules, install packages, write to target disks, update firmware, alter UEFI/EFI entries, or change bootloader state.

## What v0.1.0 observes

- CPU model/vendor fields exposed through /proc/cpuinfo.
- DMI platform and motherboard model fields, excluding serial-number files.
- PCI identifiers, modaliases and PCI-function driver binding.
- USB parent-device identifiers only; composite USB interface classes and per-interface driver bindings are not collected in v0.1.
- Block storage model/vendor and kernel driver binding when exposed through sysfs.
- DRM connector connection state and kernel-exposed modes when available; EDID monitor identification and explicit connector-to-GPU relationships are not collected in v0.1.

## Known v0.1 coverage gaps

- USB composite-device functions are not enumerated as separate `*:1.N` interface records. A parent `bDeviceClass` value of `00` stays `other`; no interface-level driver binding is claimed. See #18 for the separately versioned topology work.
- DRM connector records are not physical-monitor identities. v0.1 does not decode EDID or link a connector to its owning GPU; those relationships remain unknown until explicit topology evidence is implemented.
- An observed connector state or active mode is inventory/runtime evidence only. It is never emitted as a passed functional test.

## What it does not yet prove

- Whether a network interface can associate with an access point or reach the Internet.
- Whether a GPU can sustain a requested display mode or accelerate a desktop session.
- Whether audio output/input, Bluetooth, webcam, suspend/resume or power management work end-to-end.
- Whether a device requires a particular runtime firmware blob or whether it loaded successfully.
- Whether an external report for a similar model matches the current board revision and kernel.

These remain unknown or not-tested. A bound driver is not presented as a successful function test.

## Report and privacy

The report follows [WSM Hardware Evidence Report v1](REPORT-FORMAT.md). It uses a random per-run report ID and omits serial numbers, MAC addresses, UUIDs, hostnames, usernames, IP addresses and storage WWNs. v1 makes no network requests and performs no uploads.

The collector is deliberately standard-library-only. Upstream tools such as hwinfo, hw-probe, LKDDb-backed references and edid-decode may be added as optional evidence providers after their package, privacy, licensing and runtime behavior have been reviewed.
