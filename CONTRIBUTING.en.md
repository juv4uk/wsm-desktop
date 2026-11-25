# Contributing to WSM Desktop

> English translation. The canonical document is [CONTRIBUTING.md](CONTRIBUTING.md); the Ukrainian text takes precedence.

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

Thank you for your interest in WSM Desktop. The project is at an early stage; the most valuable contributions are verifiable technical research, small changes and accurate documentation.

## Before you start

1. Read the README and the relevant documents under `docs/`.
2. Check whether an issue or pull request on the same topic already exists.
3. For an architectural change, propose a short ADR under `docs/decisions/` first.
4. Do not add binary firmware, drivers, images or other third-party files without checking their origin, licence and redistribution rights.

## Change rules

- Keep changes narrow and reviewable.
- Do not present unverified configuration as working.
- Do not run installation commands against real disks during development.
- Do not add third-party channels, signing keys or substitute servers without separate justification.
- Preserve upstream copyright and licence notices for third-party code.
- Add an `SPDX-License-Identifier` to code and configuration where appropriate.
- Project documentation is written in Ukrainian first; translations must not contradict the Ukrainian source.

## Documentation language policy

- **Ukrainian is the canonical language for the project's documentation**, including `README.md`, `CONTRIBUTING.md`, `SECURITY.md` and all documents under `docs/`.
- **English translations** live beside the canonical file and use the `.en.md` suffix, for example `README.en.md`, `CONTRIBUTING.en.md` and `docs/ETHICS.en.md`.
- Translations are optional and may lag behind. In any disagreement, the Ukrainian original is authoritative.
- Source code, commit messages and issue discussions may use English when that makes upstream collaboration easier.
- A subdirectory README follows the language of the directory it documents unless the directory's own documentation policy says otherwise.

Do not create a translated copy as the only version of a document. Update the canonical Ukrainian source first.

## Checks

Before opening a pull request, run:

    make check

When `systems/minimal.scm` changes and Guix is available, also run:

    make check-system

Do not run `guix system init` against a physical disk during development. Integration testing belongs in a disposable virtual machine.

## Pull request

Describe:

- the problem or need;
- why the proposed solution fits the architecture;
- the components changed;
- the checks performed and their results;
- the remaining limitations.

Never include secrets, private keys, passwords or personal data in commits or logs.
