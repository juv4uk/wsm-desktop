# H170 Free — Guix substitutes

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Workflow: `.github/workflows/substitutes.yml`
- Package manifest: `drivers/profiles/h170-free-packages.scm`
- Guix lock: `channels.lock.scm` (official Guix channel only)
- Current publication state: workflow is configured; no successful H170 Free cache publication is recorded yet
- Storage: immutable GitHub Release assets for NAR files; GitHub Pages for `.narinfo`, `nix-cache-info` and `signing-key.pub`

## First package set

The initial H170 Free cache contains exactly the 11 upstream packages in the fixed manifest:

- `linux-libre`
- `mesa`
- `vulkan-loader`
- `vulkan-tools`
- `pciutils`
- `usbutils`
- `alsa-utils`
- `ethtool`
- `nvme-cli`
- `smartmontools`
- `lm-sensors`

The set is resolved using `guix time-machine -C channels.lock.scm`; it does not use a moving Guix channel revision or untrusted package-name input. The workflow builds the manifest, asks `guix publish` to sign and cache NARs, stores the NAR files as Release assets, and deploys the rewritten `.narinfo` metadata to Pages.

The initial cache is a reproducible upstream baseline for H170, not a claim of certified hardware support or a performance-tuned kernel. It contains no WSM-owned package, no Nonguix input, no proprietary NVIDIA driver, and no firmware blob. In particular, it does not establish GTX 1050 Ti 3D/compute support.

## What is not in this lane

- `wsm-tools`, `wsm-live-tools` and Compatibility live tools remain outside the public cache while issue [#367](https://github.com/juv4uk/wsm-desktop/issues/367) is unresolved. That issue does **not** block this upstream-only package set.
- NVIDIA GP107 firmware is excluded. Issue [#586](https://github.com/juv4uk/wsm-desktop/issues/586) is therefore not a prerequisite for this package set.
- The WSM channel's Phase B signing/authentication is separate from this cache: these outputs are built from the official Guix lock, not from WSM-owned channel modules. Phase B remains required before users are asked to trust/pin WSM-owned remote channel revisions such as a future `linux-libre-h170` package.
- The Nouveau atomic-KMS overlay in PR [#767](https://github.com/juv4uk/wsm-desktop/pull/767) is a separate candidate. It must pass exact-lock Scheme evaluation and a complete kernel build before it is added to a future cache manifest.

## Signing-key setup

Guix substitutes are signed. The workflow refuses to publish if the owner-controlled key pair is not configured.

On the owner's Guix machine:

```sh
sudo guix archive --generate-key
gh secret set GUIX_SIGNING_KEY --repo juv4uk/wsm-desktop < /etc/guix/signing-key.sec
gh variable set GUIX_SIGNING_PUBLIC_KEY --repo juv4uk/wsm-desktop < /etc/guix/signing-key.pub
```

The private key is stored only as the GitHub Actions secret `GUIX_SIGNING_KEY`; the public key is a repository Actions variable `GUIX_SIGNING_PUBLIC_KEY`. Never commit either key file or paste the private key into an issue, chat, or workflow log. The public key is published alongside the metadata so clients can authorize it after checking the first release provenance.

A new immutable cache release is named `h170-free-cache-<workflow-run-number>`. The workflow is triggered by relevant changes merged to `main` or by a manual dispatch on `main`; it does not accept an arbitrary package list from a workflow input.

## Client trust

After a successful publication, obtain the Pages URL and release tag from the Actions summary. Authorize the published public key with:

```sh
curl -fsS <PAGES_URL>/signing-key.pub | sudo guix archive --authorize
```

Then add the Pages URL to the daemon's `--substitute-urls` alongside the official Guix servers. Do not authorize a key merely because the file is reachable: compare it with the public key recorded in the specific release/provenance report first.

## Evidence boundary

A successful workflow proves package derivations, signed NAR generation, Release asset upload and Pages metadata deployment for the pinned manifest. It does not prove:

- runtime driver binding on the owner's H170 board;
- firmware loading or physical GPU operation;
- BIOS/UEFI boot, installer operation or disk changes;
- GP107 3D/compute, reclocking, or full performance;
- availability of the separate WSM-owned channel or its authenticated Phase B trust chain.

No ISO, NAR, or other build output is committed to a normal Git branch.
