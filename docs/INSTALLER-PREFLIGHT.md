# WSM read-only installer preflight prototype

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

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

The v1 prototype treats unknown discovery for a device marked `boot-path`, `storage-install-target`, `primary-display`, or `input` as unresolved critical evidence and refuses to emit a plan. Required runtime firmware reported as `missing` or `load-error` blocks only when attached to one of those critical roles. Network-installation uncertainty is a warning because an offline path may be available. These rules are conservative and should be reviewed against real live-image workflows before deployment integration.

## Plan determinism and trust

The plan includes the SHA-256 digest of the exact source-report bytes. `plan_sha256` is computed over canonical JSON (UTF-8, sorted keys, no insignificant whitespace) of the plan before the digest field is added. The plan includes explicit false values for mutation authorization, backend invocation, and disk access.

A draft plan is not a deployment authorization. A future apply path must independently revalidate the exact target device, backend revision, plan digest, and explicit user confirmation. Report freshness does not replace target-device revalidation.

## Safety boundary

- No subprocess is invoked.
- No network API or upload is used.
- No disk discovery or block-device access is performed by `wsm-install`.
- No package installation, firmware update, module load, or bootloader action is performed.
- The only optional write is the user-requested JSON plan file.
- A plan output path must not be confused with a target disk path.

The current hardware report schema and collector are consumed as upstream inputs. Changes to their fields belong in #5/#6, not in this prototype.
