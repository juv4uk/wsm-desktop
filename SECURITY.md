# Reporting vulnerabilities

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

WSM Desktop is pre-alpha. The installer is not yet intended for use on real systems.

## How to report

Do not publish an exploit, private data or a full technical description of an
unfixed vulnerability in a public issue.

If the repository offers **Report a vulnerability** under the Security tab, use
GitHub Private Vulnerability Reporting. If it is unavailable, open a non-public
channel to the repository owner through GitHub first, without disclosing technical
details publicly.

## Scope

- Vulnerabilities in upstream GNU Guix, Calamares, Nonguix and other dependencies
  belong with the respective upstream projects.
- Do not send signing private keys, tokens or images containing personal data.
- Until a formal security response process exists, no specific fix timeline is
  promised.

## Threat model

Especially important for this project: substitution of channels and package
sources, untrusted substitute servers, incorrect signature verification, installer
privilege escalation, wrong disk selection, and data loss through an incorrect
partitioning plan.
