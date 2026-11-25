# Hardware preflight: upstream tooling assessment

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Research snapshot: **2026-11-25**
- Scope: pre-install discovery and evidence collection for WSM Desktop
- Status: **initial assessment; not a dependency lock or final adoption decision**
- Critical path: **no** — research input, not a blocker for the first preview image
- Parent: [Issue #3](https://github.com/juv4uk/wsm-desktop/issues/3)
- Detailed audit task: [Issue #4](https://github.com/juv4uk/wsm-desktop/issues/4)

## Design rule

**Reuse the community's mature tools; make WSM responsible for orchestration, evidence semantics, privacy defaults, and a clear installer decision.**

WSM must not reimplement PCI/USB enumeration, kernel driver matching, firmware update protocols, EDID parsing, or generic hardware probing unless an upstream capability is demonstrably unavailable or unsuitable. Each fact in a WSM report must carry its source and evidence level.

The preflight must work offline, must not write to target disks, and must not upload machine data by default.

## Important distinction: five different kinds of evidence

These states must not be collapsed into a single "Linux supports this device" claim:

1. **Discovered** — the kernel or a probe tool enumerated a device and supplied an identifier.
2. **Driver candidate known** — a matching driver/module appears to exist for an identified kernel/configuration.
3. **Driver bound** — a driver is actually attached to the device in the running live environment.
4. **Firmware loaded** — required runtime firmware was available and the kernel did not report a load failure. This is distinct from device firmware update support.
5. **Function tested** — a meaningful function-specific test passed (e.g. link established, display mode active, audio endpoint enumerated and exercised).

A real-hardware report from another machine is a sixth, external evidence type. It supports confidence but does not prove that the current machine works.

## Candidate inventory

| Candidate | What it contributes | Limitations / risks | Initial WSM position |
| --- | --- | --- | --- |
| [hw-probe](https://github.com/linuxhw/hw-probe) | Full hardware snapshot, collected logs, analysis of operability, suggestions for kernel versions/drivers via Linux Hardware Database and LKDDb. Supports a local probe workflow and several packaging formats. | The documented upload flow is explicit (-upload) but collection can include sensitive machine details. Its own privacy text says redaction is best-effort and uploads salted hashes of selected identifiers. The optional -check path runs benchmarks/sanity tests (dd, hdparm, memtester, glxgears); these are not suitable as an automatic installer preflight. Its status analysis is not equivalent to WSM's per-function validation. | **Strong optional integration candidate** for local diagnostics / saved report, after a privacy and offline audit. Never invoke upload or the benchmark checks by default. |
| [openSUSE hwinfo / libhd](https://github.com/openSUSE/hwinfo) | Mature hardware probing library and CLI; used by YaST and emits detailed bus/device information including IDs, sysfs paths, module aliases and driver status. GPL-2.0. | Detailed human-readable output is not automatically a stable WSM API. Need to validate output modes, build footprint and whether linking libhd is preferable to consuming its CLI output. | **Strong inventory candidate**; compare its structured output/API against reading sysfs directly before selecting. |
| [lshw](https://ezix.org/project/wiki/HardwareLiSter) | Broad hardware inventory arranged as a tree; provides text, HTML, XML and JSON output and can combine platform, bus, storage, network and memory descriptions. | Root privileges provide more detail. JSON may include sensitive identifiers (serials, MACs); output needs strict redaction. Inventory labels such as UNCLAIMED are hints, not proof of a missing driver or a broken device. | **Optional cross-check / support-bundle source**; do not make it the canonical schema or require it in the minimal live image. |
| [inxi](https://codeberg.org/smxi/inxi) | Human-readable overview of Linux/BSD platform, hardware and runtime details; useful for support workflows. | Presentation-oriented output is not a stable machine contract and may be distro/version-sensitive. | **Human-readable diagnostic fallback only**, not the primary collector. |
| Linux kernel sysfs, PCI/USB IDs, modaliases and driver symlinks | The running kernel's authoritative view of currently enumerated devices and actual driver binding; available without an online database. | Does not by itself explain all capabilities or guarantee that the device's higher-level function works. Device enumeration depends on the current kernel and boot environment. | **Required baseline** for WSM's own read-only collector. Prefer kernel interfaces over fragile parsing of lspci prose where possible. |
| [systemd hwdb](https://www.freedesktop.org/software/systemd/man/latest/hwdb.html) / systemd-hwdb | A local key/value database matching modalias-like keys to udev properties; can enrich device identity. | It is not a complete kernel driver-support database and does not prove driver binding or functionality. The compiled database and command are tied to the systemd/udev environment; WSM must not assume the same tool is present in every backend/live image. | **Optional enrichment source** when available. Keep the normalized WSM model independent of systemd. |
| [Linux FWCTL](https://docs.kernel.org/userspace-api/fwctl/index.html) | Kernel-mediated, per-device firmware RPC transport; sysfs discovery and `FWCTL_INFO` can describe available firmware interface metadata. Vendor tools can expose selected device queries without legacy raw PCI or `/dev/mem` paths. | RPC formats and effects remain driver/device-specific. Scopes include configuration/flash access and debug writes; some operations can taint the kernel or require `CAP_SYS_RAWIO`. Presence or a query result does not establish general compatibility. | **Optional expert/service integration only** after a per-RPC allowlist and explicit consent. No FWCTL RPC in automatic preflight. |
| [LKDDb](https://github.com/cateee/lkddb) | Database generated from Linux kernel source describing hardware IDs, relevant kernel config symbols, driver names and kernel versions. Text output can be processed automatically. Repository contains GPL-2.0 and GPL-3.0 licensing material. | A kernel-source/config mapping is not proof that the running kernel enabled the driver, that a module is packaged, or that firmware/functionality works. Data must be pinned and its license/provenance reviewed before redistribution. | **Reference/index candidate** for driver-candidate explanations. Preserve source revision and distinguish its evidence from live observations. |
| [Linux Community Hardware TestDays](https://github.com/linuxhw/TestDays) | Community collection of hardware probes associated with released and upcoming distributions; repository is CC-BY-4.0 and includes real hardware reports. | Coverage is voluntary, uneven and time-dependent. A report for a similar device or distro is not a guaranteed match for the exact board revision, kernel, firmware or peripheral combination. | **External evidence source** for confidence and research links; do not turn absence of a report into incompatibility. Attribute reused data and observe the license. |
| [fwupd](https://github.com/fwupd/fwupd) + [LVFS](https://lvfs.readthedocs.io/en/latest/intro.html) | Identifies devices supported by fwupd plugins and provides signed metadata/cabinet distribution for non-volatile device firmware updates. LVFS requires explicit user consent for applying updates. | Not a universal hardware-support database and not the source for firmware blobs loaded by Linux drivers at runtime. Firmware updates may stage data in the EFI System Partition and reboot into an update path. | **Optional post-install firmware-management integration**. Preflight may read device/update availability; never perform updates during installation. |
| [libdisplay-info](https://gitlab.freedesktop.org/emersion/libdisplay-info), [edid-decode](https://git.linuxtv.org/v4l-utils.git/about/) and DRM/KMS sysfs | libdisplay-info 0.4.0 adds DisplayID v1 Type IV timings and DisplayID v2 CTA-861 blocks; edid-decode remains a useful reference/diagnostic CLI; DRM/KMS supplies live connector and mode state. | CVE-2026-112271 and CVE-2026-112272 document out-of-bounds reads in DisplayID v1/v2 parsing through 0.4.0, with possible DoS. edid-decode output format is not guaranteed stable. EDID is advertised capability, not functional pass. | **Parser adoption is conditional on verified fix/backport**; keep it optional and unprivileged. Inspect drm_info's linked libdisplay-info version, and sanitize EDID/base64 fields. Preserve KMS facts separately. |
| [Debian Installer firmware detection](https://d-i.debian.org/doc/installation-guide/nb.amd64/ch02s02.html) | Good installer precedent: missing firmware can be inferred from kernel logs and modalias information; matching firmware packages can be discovered on installation media or loaded from removable media. | Debian-specific implementation and package names cannot be copied as a WSM backend-neutral mechanism. | **Architecture reference** for offline firmware lookup and removable-media recovery. |
| [h-node](https://h-node.org/) | Community catalogue relevant to hardware freedom and whether devices work with free software. | Its purpose and evidence model differ from live driver/firmware/function diagnostics. Data reuse and machine-readable interface/terms need review. | **Policy/reference-only candidate** until its data model, licensing and integration path are verified. |

## Найновіше українське доповнення

Актуальні upstream-джерела станом на 25.11.2026, включно з hwloc 2.16.0, libdisplay-info 0.4.0, drm_info 2.10.0, PCIe AER counters, devlink health та межами VKMS/IGT, зібрані в окремому [українському доповненні](UPSTREAM-TOOLING-ADDENDUM-2026-11-25.md). Воно також фіксує privacy, read-only межі та вимогу не заявляти наявність пакунків у WSM closure до перевірки за pinned channel lock (#39).

## Key findings that affect implementation

### hw-probe should be optional and privacy-gated

The upstream README documents version **1.6.6** in the inspected snapshot and supports local collection as well as upload. The upload flow explicitly uses -upload; WSM must not pass that option implicitly. The README states that redaction is best-effort, so WSM must inspect and sanitize a local report independently before allowing any export. Its optional -check path includes performance/sanity tests; do not call it from the installer preflight.

Upstream license expression in the inspected README: **LGPL-2.1-or-later OR BSD-4-Clause**. A packaging/adoption decision must record which license path WSM relies on and preserve the required notices.

### Prefer live kernel facts over a web lookup

For the current machine, the running kernel's sysfs view can establish what it discovered, which driver is bound, and which module alias is exposed. A database such as LKDDb can explain whether a driver may exist in a given kernel source/version, but cannot override contradictory live evidence.

### Firmware has two different meanings

- **Runtime driver firmware**: blobs such as files loaded from the system firmware search paths while a kernel driver initializes. Preflight checks availability and kernel log errors; package naming and redistribution policy are backend-specific.
- **Device firmware update**: new firmware written into non-volatile device memory, often via fwupd/LVFS. This is a separate maintenance workflow and must never run automatically during OS installation.

### Display compatibility is a combination

WSM should capture at least:
- GPU device identity and the bound DRM driver;
- active DRM connectors and connected/disconnected state;
- EDID identity and advertised modes;
- current active mode, when available;
- which GPU/connector is driving the display.

An EDID mode list alone is not proof that the whole GPU-output-cable-monitor path works at the requested refresh rate.

## Proposed first live-image toolset

This is a **candidate set to validate**, not an adopted package manifest:

1. **Kernel sysfs + udev/modalias** as the baseline observation layer.
2. **One full inventory tool**: compare hwinfo with direct sysfs parsing; avoid maintaining two competing hardware identities.
3. **lspci and lsusb** as familiar diagnostics/fallbacks, not the canonical schema source.
4. **edid-decode** for monitor EDID details, paired with DRM/KMS state.
5. **A read-only kernel-log collector** for firmware/driver initialization failures, with strict redaction.
6. **Optional hw-probe integration** for a richer local support bundle, with upload and additional tests disabled.
7. **Pinned LKDDb/TestDays references** for additional evidence, with licenses and freshness recorded.
8. **Optional fwupd query** only for identifying device firmware-management capability, not flashing.

The smallest baseline must still function without Internet access and without any optional tool installed. The WSM report should record unavailable collectors as not-available, not fail the entire preflight.

## Backend packaging status

### Nixpkgs — preliminary package-index evidence

A third-party Nixpkgs package index snapshot generated on **2026-10-17** reports:

- `hwinfo` 26.0, GPL-2.0-only, from `pkgs/by-name/hw/hwinfo/package.nix`.
- `hw-probe` 1.6.6, license options LGPL-2.1 and BSD-4-Clause, from `pkgs/tools/system/hw-probe/default.nix`.
- The indexed `hw-probe` derivation has a broad runtime/input set (39 dependencies in that snapshot), including `hwinfo` and a number of optional diagnostic utilities. This reinforces the need to test its live-image footprint and avoid invoking all checks automatically.

These are package-index observations, not a build result. The index identifies a shortened nixpkgs revision (`e7fccb1ad3ed`); the exact derivation and substituter/build result must be checked against the Nixpkgs revision actually pinned by the local experiment. Sources: [hwinfo package index](https://mynixos.com/nixpkgs/package/hwinfo), [hw-probe package index](https://nixpkgs.fyi/package/hw-probe), [Nixpkgs search guidance](https://wiki.nixos.org/wiki/Searching_packages).

### GNU Guix — unresolved

No authoritative package presence/build result has been established in this research pass. Do not infer that a package is absent merely because an indexed web search did not return it. The local experiment should check the exact pinned Guix channel using its own package index and report package name/version/build status.

Issue [#4](https://github.com/juv4uk/wsm-desktop/issues/4) tracks the exact per-backend package audit. The local Nix/Guix experiment should report its actual pinned revisions and package results there rather than changing the current environment.

## Privacy defaults for WSM

- No hardware report upload by default.
- No automatic publication of serial numbers, MAC addresses, UUIDs, hostnames, usernames, IP addresses or storage identifiers.
- Separate a private local report from a deliberately sanitized export.
- Explain before export exactly what categories of information will be sent.
- Do not assume upstream redaction covers every identifier or every log format.
- Keep reports local unless the user explicitly opts in.

## Sources inspected

- [hw-probe README](https://github.com/linuxhw/hw-probe) — scope, version 1.6.6 in inspected page, operability states, check behavior, privacy and license.
- [openSUSE hwinfo README](https://github.com/openSUSE/hwinfo) — libhd/CLI, YaST use, device fields and GPL-2.0.
- [LKDDb repository](https://github.com/cateee/lkddb) — hardware IDs, Kconfig symbols, driver names, kernel versions and license files.
- [Linux Hardware TestDays](https://github.com/linuxhw/TestDays) — real-machine scope, supported distro report structure and CC-BY-4.0 license.
- [systemd hwdb](https://www.freedesktop.org/software/systemd/man/latest/hwdb.html) — modalias-like matching and local database semantics.
- [systemd-hwdb](https://www.freedesktop.org/software/systemd/man/latest/systemd-hwdb.html) — query/update interface.
- [libdisplay-info](https://gitlab.freedesktop.org/emersion/libdisplay-info) — EDID/DisplayID library; its public API is explicitly not yet stable. Also see the 2026 DisplayID parser advisories [CVE-2026-112271](https://access.redhat.com/security/cve/cve-2026-112271) and [CVE-2026-112272](https://access.redhat.com/security/cve/cve-2026-112272); do not add vulnerable 0.4.0 without a verified fix/backport.
- [v4l-utils edid-decode](https://git.linuxtv.org/v4l-utils.git/about/) — current upstream location after the standalone repository was retired in November 2024.
- [Debian Installer: devices requiring firmware](https://d-i.debian.org/doc/installation-guide/nb.amd64/ch02s02.html) — kernel-log/modalias detection and removable-media handling.
- [LVFS introduction](https://lvfs.readthedocs.io/en/latest/intro.html) and [offline firmware](https://lvfs.readthedocs.io/en/latest/offline.html) — user-authorized device firmware updates and offline distribution options.
- [Nixpkgs package search guidance](https://wiki.nixos.org/wiki/Searching_packages) — package availability must be checked against a selected branch/revision, not assumed from an unpinned web index.

The 2026-11 addendum also evaluates Linux FWCTL as an optional firmware RPC service interface (not an automatic preflight provider) and records the DisplayID parser CVEs CVE-2026-112271/112272. See [the FWCTL and DisplayID security sections](UPSTREAM-TOOLING-ADDENDUM-2026-11-25.md).

## Open questions

1. Which inventory source has the best structured output and smallest runtime footprint for the selected live image?
2. Should libdisplay-info be the WSM EDID adapter despite its currently unstable public API, or should v1 preserve raw EDID and keep parsed fields optional?
3. Can lshw provide useful cross-checks without excessive live-image size or sensitive-data exposure?
4. Can hwinfo/libhd be packaged without dragging in an unsuitable dependency stack?
5. Does a usable offline form of LKDDb data exist with a redistribution-compatible license and manageable size?
6. Which TestDays data can WSM reference without copying it, and how should dated reports be matched to exact device IDs and kernel versions?
7. What exact packages and versions are available in pinned Nixpkgs and Guix revisions used by the experiments?
8. Which hardware functions can be safely tested in a live installer without stress, writes, firmware updates or user disruption?
