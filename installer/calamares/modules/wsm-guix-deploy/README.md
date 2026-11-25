# wsm-guix-deploy module

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

This is the design location for the future Calamares Python job module. It intentionally contains no module.desc or executable entry point yet, so Calamares cannot accidentally load an incomplete installer backend.

## Required contract

The implementation must use the Python job-module API of the exact Calamares release selected by WSM. The module entry point is run(); successful execution returns None and failure returns a pair of human-readable strings.

Before deployment, it must validate:
- a single unambiguous target root;
- the expected EFI mount when UEFI installation is selected;
- all filesystem types and identifiers;
- mount state and available capacity;
- selected Free or Compatibility profile;
- the generated operating-system declaration;
- the intended bootloader target;
- the exact command and target path to be used.

## Safe execution rules

- Use Calamares' documented job command APIs; do not use os.system or shell=True.
- Never interpolate UI strings into shell commands.
- Never infer a disk from its position in a list.
- Never write before the summary and explicit confirmation.
- Do not log plaintext passwords, password hashes, tokens, or private data.
- Do not run both the Calamares bootloader job and Guix bootloader installation.
- On any failed precondition, stop before calling guix system init.

## Test strategy

Unit tests must mock the Calamares runtime and command executor. Integration tests must use disposable QEMU disks. Failure-path tests must prove that invalid or incomplete plans result in zero deployment commands.
