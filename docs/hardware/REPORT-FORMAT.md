# WSM Hardware Evidence Report v1

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Status: **initial schema proposal**
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

## Implementation guidance

Collectors keep raw observations separate from derived recommendations. Recommendations reference evidence and state confidence. Never change an unknown status into a failure simply because a lookup source or optional utility is unavailable.
