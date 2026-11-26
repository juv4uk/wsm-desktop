# WSM read-only installer preflight prototype

*English translation. The canonical document is [INSTALLER-PREFLIGHT.md](INSTALLER-PREFLIGHT.md) (Ukrainian).*

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Status: **prototype / dry-run only**
- Related: [#12 — handoff contract](https://github.com/juv4uk/wsm-desktop/issues/12), [#13 — preflight prototype](https://github.com/juv4uk/wsm-desktop/issues/13)
- Hardware input: [report schema v1](hardware/REPORT-FORMAT.md), produced by the read-only collector

## Purpose

The `wsm-install` prototype validates a local hardware evidence report, presents observed facts, and emits a deterministic backend-specific draft plan. It does not deploy a system, invoke Guix or Nix, open block devices, partition disks, or change bootloader state.

The first increment is CLI-only. It deliberately does not select or embed an installer frontend. A graphical/TUI layer can later consume the same report summary and plan functions.

## Usage

Install the pinned runtime dependency from `requirements-install.txt`, then run:

```sh
python3 -m wsm_install --preflight \
  --report tests/fixtures/hardware/desktop-observed.json \
  --backend guix --dry-run
```

Write the plan to a file instead of stdout:

```sh
python3 -m wsm_install --preflight \
  --report tests/fixtures/hardware/desktop-observed.json \
  --backend nix --dry-run --plan-output /tmp/wsm-plan.json
```

Both `--preflight` and `--dry-run` are mandatory. There is no apply command in this prototype.

## Exit codes

- `0` — report validated and draft plan emitted.
- `2` — CLI usage, file, JSON, or schema error; no plan emitted.
- `3` — required critical evidence is unresolved; no plan emitted.

## Evidence policy

The summary repeats only report facts. It does not infer a working driver from a candidate module, infer runtime firmware success from a package candidate, or infer display functionality from advertised modes.

The v1 prototype treats unknown or not-detected discovery for an explicitly reported critical role as unresolved evidence and refuses to emit a plan. It also checks whether the required `boot-path`, `primary-display`, and `input` roles are represented at all. Missing role records produce a clearly marked `diagnostic-only` plan with `plan_readiness.confirmable=false`; absent records are never interpreted as proof of success.

`storage-install-target` is not a role the collector may select. The prototype always marks explicit user target selection and immediate target-identity revalidation as outstanding user actions. Therefore, every v0.1 output is diagnostic-only and never a confirmable deployment plan. Required runtime firmware reported as `missing` or `load-error` blocks only when attached to an explicitly critical role. Network-installation uncertainty is a warning because an offline path may be available.

## Plan determinism and trust

The plan includes the SHA-256 digest of the exact source-report bytes and report-local JSON Pointer references to the evidence and functional-test records used for each device summary. `plan_sha256` is computed over canonical JSON (UTF-8, sorted keys, no insignificant whitespace) of the plan before the digest field is added. The machine-readable `execution.dry_run` marker is true; plan confirmation, mutation authorization, backend invocation, and disk access are all false.

The CLI backend aliases are explicit: `guix` maps to `guix-system`, and `nix` maps to `nixos`.

A draft plan is not a deployment authorization. A future apply path must independently revalidate the exact target device, backend revision, plan digest, and explicit user confirmation. Report freshness does not replace target-device revalidation.

## Safety boundary

- No subprocess is invoked.
- No network API or upload is used.
- No disk discovery or block-device access is performed by `wsm-install`.
- No package installation, firmware update, module load, or bootloader action is performed.
- The only optional write is the user-requested JSON plan file.
- Plan output must be a regular file in an existing directory; symlinks, block/character devices, `/dev`, `/proc`, and `/sys` destinations are refused.
- The output path must not resolve to or hard-link the source report or schema.
- The plan is written to a same-directory temporary file and atomically replaced only after serialization succeeds.

The current hardware report schema and collector are consumed as upstream inputs. Changes to their fields belong in #5/#6, not in this prototype.
