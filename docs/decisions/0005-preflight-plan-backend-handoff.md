# ADR 0005: Preflight → план → один системний backend

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **proposed — на рев'ю**
- Дата: 2026-11-25
- Пов'язані завдання: [#12](https://github.com/juv4uk/wsm-desktop/issues/12), [#10](https://github.com/juv4uk/wsm-desktop/issues/10), [#2](https://github.com/juv4uk/wsm-desktop/issues/2)
- Залежні матеріали: [#5](https://github.com/juv4uk/wsm-desktop/issues/5), [#6](https://github.com/juv4uk/wsm-desktop/issues/6), [#22](https://github.com/juv4uk/wsm-desktop/issues/22), [#23](https://github.com/juv4uk/wsm-desktop/issues/23)

## Контекст

WSM needs a hardware-first installer. Calamares is no longer the assumed frontend; the current hypothesis in #10 is a thin WSM-owned guided frontend (`wsm-install`) following the archinstall interaction model: guided steps, an inspectable JSON plan, profiles, and a QEMU-only test loop.

The hardware lane produces a versioned, offline, read-only evidence report (schema v1.0.0 draft in PR #9). The backend lane defines two mutually exclusive native install paths: Guix System (`guix system init`) and NixOS (`nixos-install`), as recorded in ADR 0004.

This ADR defines only the **handoff contract** between those pieces. It does not define schema fields, collector behavior, scenario verdict semantics, or the freshness/session protocol; those remain owned by #5/#6, #22, and #23 respectively.

## Terminology

- **Evidence report** — the versioned JSON document emitted by `wsm-hwcheck`. WSM consumes it; it does not redefine it.
- **Preflight** — the read-only phase that loads and validates the report and presents what is known and unknown to the user.
- **Plan** — a deterministic, serializable, backend-specific description of the intended installation, produced only after preflight passes.
- **Backend adapter** — the code that renders a confirmed plan into a native configuration and invokes exactly one native installer.
- **Native installer** — `guix system init` for a Guix plan, or `nixos-install` for a Nix plan.

## Proposed contract

### 1. Versioned interfaces

The contract has three independently versioned artifacts:

| Artifact | Version source | Consumer rule |
| --- | --- | --- |
| Evidence report | `schema_version` in the report | Only explicitly supported versions are accepted; unknown versions block preflight. |
| Install plan | `plan_version` emitted by `wsm-install` | Backend adapters must declare the exact plan versions they accept. |
| Backend adapter | adapter-declared version | Recorded in the plan so a plan can be audited against the adapter that made it. |

No field is added to the hardware report by this ADR. A report from a different live boot is not proof of current-session identity; #23 owns that protocol. Until it is defined, a report without a freshness assertion is marked **unverified freshness** and cannot be the sole basis for a confirmed plan.

### 2. Ordered phases

1. **Collect/load report.** `wsm-hwcheck` runs read-only, or the installer loads an existing report. The report is parsed and validated against its declared supported schema version.
2. **Preflight gate.** The installer displays per-device evidence states (detected, driver-bound, firmware present, functional-tested, unknown) together with source and collection time. A missing, malformed, unsupported-version, or unverified-freshness report blocks plan generation. Scenario-critical unknowns are resolved according to #22/#24 policy or require an explicit, recorded user waiver; silent continuation is forbidden.
3. **Plan generation.** After the gate passes, the frontend emits a deterministic JSON plan for exactly one selected backend. The plan records the backend id, adapter version, target device identifiers, mount layout, locale/timezone/keyboard intent, profile intent, and the pinned channel/flake revisions used for the build. It must be reviewable before any write.
4. **Confirmation.** The user explicitly confirms the plan. Any later change invalidates the confirmation and requires a new one.
5. **Handoff.** The matching adapter renders the native configuration and calls its native installer exactly once. The adapter, not the frontend, owns bootloader installation, root filesystem activation, service definitions, and generations.

### 3. Hard boundaries

- **One backend owns one installed system.** A plan has exactly one backend id. Guix and Nix plans are never merged, and neither adapter may invoke the other's installer.
- **No store merging.** `/gnu/store` and `/nix/store` are not interchangeable; neither adapter imports derivations from the other as equivalent artifacts.
- **No frontend disk writes.** Before confirmation the installer performs read-only probes only. All partitioning, formatting, mounting, and bootloader writes happen inside the selected backend's native installer.
- **Dry-run stops before writes.** `--dry-run` may emit the plan and evidence summary but must exit before any disk or bootloader operation and before any adapter invocation.
- **Offline by default.** No probe upload, telemetry, or network fallback occurs implicitly. Uploading a report is a separate, explicit, voluntary action with its own confirmation.
- **No host shortcuts in tests.** Integration tests use disposable qcow2 images and virtual serial consoles only; host block devices, EFI variables, and physical firmware updates are out of scope.

### 4. Failure behavior

| Condition | Required behavior |
| --- | --- |
| Report file missing | Block; exit non-zero; emit no plan; no disk access. |
| Malformed JSON or unsupported `schema_version` | Block; show the exact validation failure; emit no plan. |
| Freshness unproven (#23 open) | Mark `unverified freshness`; block confirmation by default. |
| Scenario-critical unknown | Block or require explicit recorded waiver; never silently continue. |
| Plan contains zero or multiple backend ids | Reject the plan before confirmation. |
| Adapter/plan version mismatch | Reject before invoking the native installer. |
| User does not confirm | No adapter invocation, no disk writes. |
| Dry-run requested | Stop after plan emission; no writes, no adapter invocation. |

## Acceptance assertions

These are the intended test assertions for #13/#14. They describe observable behavior; implementation details remain open.

1. **A1 — no report:** invoking preflight without a report exits non-zero, emits no plan, and performs zero write operations on block devices.
2. **A2 — invalid report:** malformed JSON, a missing required top-level field, or an unsupported `schema_version` exits non-zero and emits no plan.
3. **A3 — deterministic plan:** a valid fixture report with fixed inputs produces byte-identical JSON plans across two runs at the same contract version.
4. **A4 — single backend:** a plan with no backend id or with both `guix` and `nix` ids is rejected.
5. **A5 — adapter match:** the invoked adapter version equals the adapter version recorded in the confirmed plan, and the native installer is invoked exactly once.
6. **A6 — explicit confirmation:** without a confirmation token/action, no adapter is invoked and no write operation is attempted.
7. **A7 — dry-run:** `--dry-run` exits zero after emitting the plan, with zero write operations and zero native-installer invocations.
8. **A8 — offline:** in default mode, no network socket is opened and no upload endpoint is contacted.
9. **A9 — immutability:** mutating a confirmed plan invalidates its confirmation; a second confirmation is required before handoff.
10. **A10 — freshness dependency:** a report without the #23 freshness assertion is blocked by default; the test is updated only when #23 defines the protocol.
11. **A11 — disposable targets:** a plan referencing a host block device path is rejected by the test harness; only disposable image paths are accepted.
12. **A12 — evidence visibility:** the preflight output includes `schema_version`, `report_id`, `collected_at`, `environment.architecture`, `environment.kernel_release`, `environment.boot_mode`, and a per-device known/unknown summary from `devices`, without inventing new report fields.

## Open dependencies

- **#23 (freshness/session identity):** the exact privacy-safe assertion is not yet defined. This ADR deliberately blocks unverified reports rather than guessing a format.
- **#22/#24 (scenario policy):** which unknowns count as scenario-critical is owned by the hardware/installer policy lane.
- **#5/#6 (schema/collector):** the report schema remains a draft in PR #9; this ADR consumes its public top-level fields only.
- **#11 (installer evaluation):** the final frontend choice may change the presentation layer but not these phase boundaries.

## Decision

Adopt this contract as a **proposed** interface for the installer prototype. It becomes binding for implementation only after review in #10 and #2 and after the open dependencies above are resolved.

## Links

- [ADR 0004 — Nix і GNU Guix як окремі кандидати на системну основу WSM](0004-nix-guix-backend-strategy.md)
- [ADR 0002 — Calamares як графічний інсталятор](0002-calamares-as-installer.md)
- [Issue #12 — preflight → plan → single-backend handoff contract](https://github.com/juv4uk/wsm-desktop/issues/12)
- [Issue #23 — report freshness contract](https://github.com/juv4uk/wsm-desktop/issues/23)
