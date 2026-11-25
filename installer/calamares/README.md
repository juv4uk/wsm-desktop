# Calamares integration

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

This directory is reserved for WSM's Calamares configuration, branding, module configuration, and translations.

## Current status

No production settings.conf or runnable WSM deployment module is committed yet. The first task is a feasibility check: determine whether the selected Calamares release and its Qt/KPMcore/Python dependencies can be built and run in the intended Guix live environment.

## Planned contents

- settings.conf — WSM module sequence, version-controlled with the Calamares release.
- branding/wsm/ — WSM-owned branding, artwork, and slideshow.
- modules/wsm-guix-deploy/ — WSM-owned Python job module, after API validation.
- modules/wsm-guix-config/ — future UI module for Guix-specific configuration, if existing Calamares views are insufficient.

Do not copy upstream Calamares module configuration blindly. Keep upstream notices, check the matching version's module documentation, and record local changes.

See docs/INSTALLER.md and docs/decisions/0002-calamares-as-installer.md.
