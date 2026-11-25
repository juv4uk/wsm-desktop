# Contributing to WSM Desktop

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

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

The repository previously mixed languages without a stated rule: the README was
English while `CONTRIBUTING.md` and `SECURITY.md` were Ukrainian, and nothing said
which file a translator should treat as the original. The rule is now explicit and
is checked by `scripts/check_docs.py`.

- **Entry points are canonical in English.** `README.md`, `CONTRIBUTING.md` and
  `SECURITY.md` — the three files a first-time visitor reads.
- **Design and research documents are canonical in Ukrainian.** Everything under
  `docs/`, including the ADRs, the roadmap, and the hardware and testing notes.
- **Subdirectory READMEs follow the language of the directory they document.**
- **Translations sit beside the original and carry a language suffix.** A Ukrainian
  translation of `CONTRIBUTING.md` is `CONTRIBUTING.uk.md`; an English translation of
  `docs/ETHICS.md` is `docs/ETHICS.en.md`. A translation is never the only copy of a
  document, and it must name the canonical file it follows.
- Translations are optional and may lag. The canonical document is the source of
  truth in any disagreement.

If a document genuinely belongs in the other language, move the whole document
rather than adding a second copy under a different name.

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
