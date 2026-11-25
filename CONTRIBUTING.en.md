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

## Pull request

Describe:

- the problem or the need;
- why the proposed solution fits the architecture;
- the components changed;
- the checks performed and their results;
- the limitations that remain.

Never include secrets, private keys, passwords or personal data in commits or logs.
