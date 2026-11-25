# Installer report freshness and revalidation contract

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Status: **consumer-side proposal; producer/schema approval required**
- Related: #12 (handoff contract), #17 (canonical handoff documentation), #23 (freshness contract), #5/#6 (schema and collector owners), #14 (QEMU integration)
- Prototype: `wsm_install/freshness.py`
- Tests: `tests/test_installer_freshness.py`

## Problem

A report can be valid JSON, pass schema validation, and still describe a previous boot or a device topology that has since changed. A recent wall-clock timestamp alone is not proof of freshness: the live clock may be wrong, unset, or adjusted while an offline installer is running.

The existing schema v1.0.0 contains `collected_at`, architecture, kernel release, boot mode, and report-local device records. It does not contain a per-boot identity or a monotonic collection timestamp. Because schema v1.0.0 rejects additional properties, this proposal does not modify it.

## Proposed evidence envelope for a future schema revision

The collector should provide the following values in a versioned schema extension:

- `boot_session_sha256`: SHA-256 over a domain-separated kernel boot ID. The raw boot ID is never included in the report. It changes on reboot and is stable during one boot.
- `collected_monotonic_ns`: collection completion time from `CLOCK_BOOTTIME`, not wall-clock time. It is comparable only when boot-session digests match.
- `architecture`, `kernel_release`, `boot_mode`: the exact collection environment.
- `topology_sha256`: the current prototype hashes a canonical, report-local **device inventory** list of category, bus, discovery status, and non-sensitive hardware IDs. It does not yet hash relationship edges (for example, controller/interface or GPU/DRM/connector links); until #18's relationship contract is ratified and included, this digest must not be described as a complete topology-graph fingerprint. Do not include serial numbers, MAC addresses, host paths, UUIDs, hostnames, or raw EDID.
- Existing `collected_at` remains useful for human audit but is not the authoritative freshness clock.

The session digest is not a persistent machine identifier. It permits comparison only within one boot session; it must not be reused as a cross-boot identity.

## Decision order

At plan confirmation, the consumer must perform a new read-only session/topology observation and compare it with the report bound to the draft plan:

1. Verify the exact report SHA-256 equals the digest embedded in the plan.
2. Verify both report and live-session boot digests are valid and equal.
3. Verify the monotonic clock is available and non-regressing; calculate age only within the matching boot session.
4. Reject a report older than the configured maximum age (prototype default: 600 seconds).
5. Require architecture, kernel release, and boot mode to match exactly.
6. Require the canonical topology digest to match.
7. Only then mark the report fresh and permit the user to continue to a separate confirmation step.

The prototype evaluator is pure and does not read files, probe hardware, invoke a backend, or access disks. The caller must hash the exact raw report bytes and supply that digest as `report_sha256`; the evaluator compares the supplied digest with the plan-bound value but does not open or hash a report file itself. It returns a distinct status and a reason for each failure class.

## Status semantics

| Status | Meaning | Freshness gate passed |
|---|---|---:|
| `fresh` | Report bytes, boot session, age, environment, and topology match | Yes |
| `stale` | Same boot, but collection age exceeds policy | No |
| `session-mismatch` | Report belongs to another boot | No |
| `report-digest-mismatch` | Report bytes differ from the plan-bound report | No |
| `environment-mismatch` | Architecture, kernel, or boot mode changed | No |
| `topology-changed` | Relevant device inventory changed | No |
| `unverifiable` | Required freshness evidence is absent or inconsistent | No |

A freshness failure is not evidence of hardware incompatibility. It means the report must be recollected or the user must return to preflight.

**Important boundary:** `freshness_gate_passed = true` means only that this isolated freshness sub-check succeeded. It does **not** make the complete installation plan confirmable, authorize a backend, select or validate a target disk, satisfy scenario capability requirements, or permit disk writes. The current #19 `wsm-install` output remains `diagnostic-only` and `plan_readiness.confirmable=false`. The freshness evaluator is not wired into that CLI until #5/#6 approve a versioned producer envelope and the complete scenario/target confirmation path is implemented.

## Plan binding and target safety

The draft plan must bind to the exact report digest and boot-session digest. Any change to either invalidates the plan. A changed topology requires a new report and new plan.

Freshness is not target-disk identity. Immediately before any future destructive operation, the installer must independently re-identify the selected target device, compare its identity with the user's explicit selection, and require a separate confirmation. No freshness result authorizes disk writes.

## Privacy and safety

- Never store the raw kernel boot ID in an exported report.
- Never add persistent machine identifiers to correlate reports across boots.
- Never include serial numbers, MAC addresses, host paths, or network identifiers in the topology digest.
- The preflight and freshness check remain offline and read-only.
- Unknown clock/session/topology evidence fails closed for confirmation, but must not be mislabeled as unsupported hardware.

## Open producer decisions

This proposal requires #5/#6 owners to confirm field names, collection points, and backward-compatibility strategy before integration. The existing v1.0.0 schema and collector are intentionally unchanged. A QEMU reboot test belongs to #14 and should prove that a report from boot A cannot be confirmed after boot B.
