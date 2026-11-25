# Contributing to WSM Desktop

> English translation. The canonical document is
> [CONTRIBUTING.md](CONTRIBUTING.md); in any disagreement the Ukrainian text wins.

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Thank you for your interest in WSM Desktop. The project is at an early stage; the
most valuable contribution right now is verifiable technical research, small
changes and accurate documentation.

## Before you start

1. Read the README and the relevant documents under `docs/`.
2. Check whether an issue or pull request on the same topic already exists.
3. For an architecture change, propose a short ADR under `docs/decisions/` first.
4. Do not add binary firmware, drivers, images or other third-party files without
   verifying origin, licence and redistribution rights.

## Change rules

- Keep changes narrow and reviewable.
- Do not present unverified configuration as working.
- Do not run installation commands against real disks during development.
- Do not add third-party channels, signing keys or substitute servers without
  separate justification.
- For third-party code, preserve upstream copyright and licence notices.
- Code and configuration must carry an `SPDX-License-Identifier` where appropriate.
- Every document states its language and status at the top, as described below.

## Documentation language policy

The canonical language for **all project documentation is Ukrainian**. This applies to `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and every document under `docs/`.

- **English translations** live next to the canonical file and use the `.en.md` suffix, for example `README.en.md`, `CONTRIBUTING.en.md`, and `docs/ETHICS.en.md`.
- A translation is never the only copy of a document; it must identify the canonical Ukrainian source.
- Translations are optional and may lag. The Ukrainian canonical document is authoritative in any disagreement.
- Source code, commit messages, and issue discussions may use English when that makes upstream collaboration easier.

Do not create a translated copy as the only version of a document. Update the Ukrainian canonical source first.

## Checks

Before a pull request, run:

    make check

When `systems/minimal.scm` changes and Guix is available:

    make check-system

Do not run `guix system init` against a physical disk to test a change. Integration
testing happens on a disposable virtual machine.


## Test quality and agent workflow

Tests should protect behavior, not confirm that an agent wrote an expected line. Before adding a test, name the concrete regression it is meant to catch.

- A new test must be **red without the fix and green with it**. Exercise the real function, CLI, contract, or security boundary—not just grep a file or assert a value that the test itself created.
- Do not add tests for exact large generated-file contents, global record counts, or a declarative config line. Evaluate Scheme with Guix; test the real invariant a configuration is meant to provide.
- Do not test a stub's behavior instead of the real component. When the real environment is unavailable, label structural checks as limited evidence.
- Extend the existing test file for the relevant subsystem. A separate test file is justified only for a new independent contract or runner.
- Start with the narrowest relevant tests, then run the full `make check` once before finishing the change. Do not rerun a suite just to get different output or in the hope that a random failure disappears.
- Preserve complete test output in a log; do not pipe a test process through `grep`, `head`, or `tail` when that could hide the failure.
- If a test in an untouched subsystem fails, run it once against the base commit. If it fails there too, record the pre-existing defect separately instead of masking it in the current PR.

### Agent coordination and merging

- Before starting, inspect the current issues, open pull requests, and latest `main`; do not create a parallel implementation of an existing solution.
- Each PR has one coherent purpose. Do not edit the same file concurrently across branches without explicit coordination; make ownership clear and integrate finished changes sequentially.
- Synchronize the branch with the latest `main` before review. After new commits land, re-check the current HEAD—not a previously green SHA.
- `queued`, `pending`, `cancelled`, missing, or stale CI is not a successful check. Merge only after required checks complete on the exact HEAD, with no conflicts and a reviewed diff.
- Report the exact commit, commands, results, and remaining limits. Never present a synthetic fixture as hardware evidence or attribute QEMU results to physical hardware.

### Evidence levels and safety

- Distinguish static/unit checks, Guix evaluation/build, QEMU with TCG, QEMU with KVM, and physical hardware. Each level proves only what was actually run there.
- Use disposable `qcow2` disks for installer integration tests. Before starting, verify that the VM is not attached to host disks; never experiment on disks containing valuable data.
- Until a separately reviewed and authorized APPLY path exists, the installer only emits a plan. Do not run `mkfs`, `mount`, `guix system init`, or other disk-changing operations on a developer machine.
- Pin upstream sources to immutable revisions and retain checksum/signature evidence. Do not import foreign build recipes without review or execute downloaded upstream scripts simply because an updater found them.
- If state updates or migrations are added later, they need explicit ownership, idempotency, user/system scope separation, and defined partial-failure behavior. Do not run silent background migrations that bypass visible user confirmation.

## Pull request

Describe:

- the problem or the need;
- why the proposed solution fits the architecture;
- the components changed;
- the checks performed and their results;
- the limitations that remain.

Never include secrets, private keys, passwords or personal data in commits or logs.
