# Ethical principles and third-party components

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

> English translation. The canonical document is [ETHICS.md](ETHICS.md); in any
> disagreement the Ukrainian text wins.

## Free software — the default path

WSM Free is the base profile. It must not depend on Nonguix, proprietary firmware
or closed drivers.

The project's aim is not to hide compromises but to give the user accurate
information so that the choice can be made knowingly.

## Nonguix — a separate optional channel

Nonguix is an independent community channel for Guix. Its own README states the
limitations and caveats of nonfree software and asks that the channel not be
promoted as an officially recommended GNU Guix component.

WSM Desktop may document how to enable it as a compatibility option, but:

- does not describe Nonguix as part of official Guix;
- does not enable the channel in the Free profile;
- does not conceal the nonfree status of packages;
- does not treat all content of the channel as equally licensed;
- does not redistribute firmware or blobs before their licence terms are checked.

## Permission to redistribute

A package existing in a third-party channel does not by itself grant the right to
include it in a WSM ISO. For every component intended for redistribution, record:

- name and exact version;
- upstream URL and revision;
- licence or terms of use;
- source of the binary file;
- whether the licence permits mirroring and redistribution;
- whether the user must download it separately.

If the right to redistribute is not confirmed, the component does not go into the
image.

## Binary substitutes and trust

A binary substitute server is a separate supplier of binary artefacts. Its signing
key is not added automatically just because the server is mentioned in Nonguix
instructions.

Before authorising a key, verify its provenance through the upstream source and
document the trust boundary. Do not insert keys, tokens or arbitrary URLs into
system configurations without an explicit decision.

## Information for the user

When the installer offers Compatibility, it must explain:

- what exactly is being added;
- why this component may be needed;
- whether it is free software;
- what audit and security limitations it creates;
- whether it will be downloaded from the network or included on the ISO.

## Trademarks and independence

GNU, GNU Guix, Nonguix and Calamares retain their own names, logos and trademarks.
WSM Desktop does not use them in a way that suggests official endorsement,
partnership or origin.
