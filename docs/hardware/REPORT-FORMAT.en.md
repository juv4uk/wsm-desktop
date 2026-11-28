# WSM Hardware Evidence Report v1

*English translation. The canonical document is [REPORT-FORMAT.md](REPORT-FORMAT.md) (Ukrainian).*

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Status: **initial schema proposal; current revision 1.1.0**
- Critical path: **yes** — preflight and the installer plan both consume this schema
- Schema: [hardware-report.schema.json](../../schemas/hardware-report.schema.json)
- Parent: [Issue #3](https://github.com/juv4uk/wsm-desktop/issues/3)
- Work item: [Issue #5](https://github.com/juv4uk/wsm-desktop/issues/5)

## Purpose

The report is a backend-neutral evidence record produced by the live environment before installation. It is not a hardware certification, benchmark result, or global compatibility score.

It preserves the distinction between observations made on the current machine, external database records, and functions actually tested.

## Versioning

The first schema is 1.0.0 and targets JSON Schema Draft 2020-12.

- A breaking change increments the major version.
- A backward-compatible optional-field addition increments the minor version and requires a published schema for that exact minor version plus explicit consumer support.
- Clarifications that do not change validation behavior increment the patch version.
- Producers write the exact schema version. Consumers select the validator for that exact version and reject unsupported versions with an explanation rather than silently misreading them.

The v1.0.0 schema sets `additionalProperties: false` for its closed objects. Therefore, a v1.0.0 consumer does **not** generically tolerate unknown properties. A new optional field is accepted only after the corresponding schema revision and consumer support are released. Do not advertise forward-field tolerance that the selected schema validator does not implement.

### Current revision: 1.1.0

The current published schema is **1.1.0** ([hardware-report.schema.json](../../schemas/hardware-report.schema.json)). It only adds optional fields, so a 1.0.0 report describes a subset of the format and stays valid.

The frozen 1.0.0 copy sits beside it: [hardware-report-1.0.0.schema.json](../../schemas/hardware-report-1.0.0.schema.json). A report is validated against **the schema it declares** (`wsm_install/report_schema.py`), not against the current one: the current file pins `schema_version` to 1.1.0 and would reject a valid 1.0.0 report. A version that is not published is refused with the version named in the message rather than read approximately.

What 1.1.0 adds:

- `environment.boot_mode_evidence` - why `boot_mode` is what it is (which source was present or absent);
- `environment.platform.bios_release`, and `bios_date` is now populated from DMI and normalised from `MM/DD/YYYY` into an ISO date;
- `devices[].cpu` - `family`, `model_number`, `stepping`, `microcode`, `logical_processors`;
- `devices[].gpu` - `boot_vga`, `drm_cards`, `pci_link`;
- `devices[].network` - interfaces whose sysfs link resolves to exactly this PCI function;
- `devices[].storage` - `capacity_bytes`, logical and physical sector sizes, `rotational`, `removable`, `read_only`, `transport`, `partitions`.

Each of these objects carries `unavailable`: the facts no readable source provided. That is `unknown`, stated explicitly. A filled-in approximate value instead of `unavailable` is a defect, not a convenience.

## Evidence model

For each device, store separate facts:

- discovery: discovered / not-detected / unknown;
- driver: bound / module-loaded-unbound / available-only / none-known / error / not-applicable / unknown;
- runtime firmware: loaded / available-not-confirmed-loaded / missing / load-error / not-needed / unknown;
- every function test: passed / failed / partial / not-run / unsupported / unknown.

A driver candidate reported by a package index or kernel configuration database does not mean the running kernel loaded or bound it.

Runtime firmware loading is separate from a device firmware update. A successful device firmware update capability says nothing about whether a kernel driver has its required runtime blob.

A function test documents its method and result. A read-only inventory check may prove that a connector exists, but not that an end-to-end task works.

## Evidence provenance

Each evidence item records its kind, source/tool and optional version/URL, observation time, confidence label, concise summary, and optional reference.

Use confirmed only for a directly observed fact or reproducible test. An external database entry normally remains strong or limited depending on the exactness of hardware and kernel matching. Use unknown where source quality or matching is unclear.

## Privacy

The strict-local profile is the default. Reports must not include serial numbers, MAC addresses, UUIDs, hostnames, usernames, IP addresses or storage WWNs. The report ID is a random per-report identifier, not a stable host identifier.

Network upload is false in v1. An export workflow must create a separate sanitized copy and show the data categories before asking for consent. Never assume an upstream tool's redaction is sufficient.

## Display data

A display record distinguishes monitor identity decoded from EDID, connector identity and connection state, advertised modes, active mode observed through DRM/KMS, and active refresh rate where available.

Advertised modes are not proof that every mode works through the actual GPU, connector, cable and monitor path.

## Synthetic fixtures

The fixtures in this directory are synthetic and contain no real machine report:
- [desktop-observed.json](../../tests/fixtures/hardware/desktop-observed.json)
- [missing-firmware.json](../../tests/fixtures/hardware/missing-firmware.json)
- [unknown-incomplete.json](../../tests/fixtures/hardware/unknown-incomplete.json)

The fixtures stay in the 1.0.0 format on purpose: they prove that an old report still validates against its own schema. The 1.1.0 facts are covered by the synthetic sysfs tree in `tests/test_hwcheck.py` and by the test documents in `tests/test_hardware_report.py`, not by a new fixture from a real machine.

## Implementation guidance

Collectors keep raw observations separate from derived recommendations. Recommendations reference evidence and state confidence. Never change an unknown status into a failure simply because a lookup source or optional utility is unavailable.

## Native Free Pascal tools

WSM provides five separate Guix packages to keep runtime closures small:

- `wsm-hwcheck-fpc` is a read-only PCI identity and direct-driver-binding collector. It emits the Hardware Evidence Report 1.1.0 envelope, but this slice collects PCI devices only; CPU, USB, block, DRM, firmware-log and functional-test facts remain uncollected rather than inferred.
- `wsm-classify-fpc` produces the diagnostic subsystem summary under the same contract as `wsm_install/classification.py`. `certified` remains zero; the result is not installation authorization.
- `wsm-partition-fpc` is a read-only GPT planner. It validates the whole-disk target, operator acknowledgement and size drift, then emits commands as data; it never invokes `sgdisk` or changes a partition table.
- `wsm-profile-fpc` performs a preliminary semantic check of an evidence bundle: schema version, relative-path syntax, duplicate paths, artifact presence and at least one passing function. It is not a complete JSON Schema validator and does not verify SHA-256; it explicitly reports digest verification as `delegated`, so it does not replace the full Python validator.
- `wsm-preflight-fpc` checks tools, Guix, privilege, mount-point availability, the system declaration, hardware-report presence and ISA before installation; it distinguishes `fail` from `not-run` and never changes the system.

All five packages use `LicenseRef-Volnist` / `ВОЛЬНІСТЬ`. FPC is a build-time `native-input`, not a runtime dependency; none of these packages pulls in the Python interpreter.

Build locally with FPC 3.2.2 using `make -C tools/pascal clean all`. Build all four Guix packages with `make build-fpc-packages`. The **Free Pascal build** workflow compiles all four executables, validates the Hardware Evidence Report 1.1.0 schema and compares the PCI collector and classifier with their Python references; it also runs CLI runtime tests for the partition planner and profile preflight reader. These packages are not considered verified until compilation and runtime checks pass.
