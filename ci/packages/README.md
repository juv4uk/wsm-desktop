# H170 Free package set

**Status: BUILD-ONLY / NOT-PUBLISHED.** This manifest resolves the package set
against the exact official Guix revision in \`channels.lock.scm\`. It can be
used for pinned evaluation and ephemeral CI builds. It is not permission to
export NARs, upload package binaries, publish substitutes, or claim hardware
acceptance.

## Target

- Gigabyte GA-H170-Gaming 3
- Intel Core i5-6400 (Skylake)
- Intel HD Graphics 530
- NVIDIA GeForce GTX 1050 Ti, Pascal GP107, PCI ID \`10de:1c82\`
- Kingston NVMe, Samsung SATA storage, HDA audio, Killer E2200 Ethernet label

The canonical device facts remain in
[\`drivers/profiles/h170-free.json\`](../../drivers/profiles/h170-free.json).
Unknown PCI IDs and runtime bindings are intentionally not inferred.

## Included upstream Guix packages

\`h170-free.scm\` is the authoritative Guix manifest. Its explicit roots are:

| Package | Hardware role |
| --- | --- |
| \`linux-libre\` | H170 platform kernel; i915, nouveau, alx, NVMe, AHCI and HDA drivers live in the kernel |
| \`mesa\`, \`mesa-utils\` | Open graphics stack and diagnostics |
| \`vulkan-loader\`, \`vulkan-tools\` | Vulkan loader and diagnostic tools; not a promise that GP107 Vulkan is functional |
| \`intel-media-driver\`, \`intel-vaapi-driver\`, \`libva-utils\` | Intel HD 530 media-driver candidates and VA-API diagnostics |
| \`igt-gpu-tools\` | Intel DRM/GPU diagnostics |
| \`pciutils\`, \`usbutils\`, \`dmidecode\`, \`lshw\` | Platform inventory |
| \`nvme-cli\`, \`smartmontools\` | NVMe/SATA diagnostics |
| \`alsa-utils\` | HDA audio diagnostics |
| \`util-linux\`, \`e2fsprogs\`, \`parted\`, \`gptfdisk\`, \`dosfstools\` | Storage and filesystem tooling |
| \`iproute\`, \`iw\`, \`ethtool\` | Wired networking and generic wireless/network diagnostics |

All roots come from the official Guix package modules at
\`4e5195be20d9b124df8a8bb69213412236e4668e\`; their transitive dependencies
are resolved by Guix. This manifest does not copy or fork upstream recipes.

## Deliberate exclusions

- **\`wsm-tools\` and all WSM-owned package definitions:** excluded until issue
  [#367](https://github.com/juv4uk/wsm-desktop/issues/367) resolves the
  \`LicenseRef-Volnist\` / Guix package metadata mismatch and the owner approves
  a precise Free distribution model.
- **NVIDIA / Nouveau firmware and \`linux-firmware\`:** excluded. The GP107 Free
  profile marks FECS/GPCCS firmware required for full 3D/compute; issue #586
  records the NVIDIA firmware redistribution condition and prohibits WSM
  redistribution absent written legal clearance.
- **NVIDIA 580.x proprietary driver:** not resolved as a Guix package and not
  part of Free. The Compatibility candidate remains separate and unbuilt.
- **No Nonguix input is imported** by this manifest; it uses only
  \`channels.lock.scm\`, never \`channels/compatibility.lock.scm\`.
- Wi-Fi/Bluetooth and other unidentified peripherals: not guessed into the
  hardware set.

## Evidence and known limitations

1. The current lock resolves linux-libre 7.3.5. The project records a GP107
   Nouveau atomic-KMS regression risk for this candidate; package resolution
   or compilation does not clear that risk.
2. GP107's FECS/GPCCS firmware is required for full Nouveau 3D/compute. Without
   a lawful, separately approved firmware path, do not claim Free 3D/Vulkan
   support for the GTX 1050 Ti.
3. Package build success proves only that the Guix derivations build. It does
   not prove PCI binding, display modesetting, VA-API, Vulkan, audio playback,
   network traffic, suspend/resume, or native H170 acceptance.
4. Hardware statuses remain those in the JSON profile. Do not promote
   \`not-assessed\` / \`unknown\` to \`pass\`.

## Build commands

Pinned resolution only:

\`\`\`sh
guix time-machine -C channels.lock.scm -- build \\
  -m ci/packages/h170-free.scm --dry-run --no-grafts
\`\`\`

Build into the local Guix store (no archive export):

\`\`\`sh
guix time-machine -C channels.lock.scm -- build \\
  -m ci/packages/h170-free.scm --no-grafts
\`\`\`

The manual GitHub Actions workflow
[\`h170-free-package-build-evidence.yml\`](../../.github/workflows/h170-free-package-build-evidence.yml)
does the same ephemeral build and writes only store-path metadata, recursive
SHA-256 hashes, and \`guix size\` reports to the workflow summary. It does not
upload artifacts, NARs, releases, or substitutes.

## Publication gate

Binary publication remains disabled by the mainline safety decision
(\`732bb17b07f359108e179643c9683237a8fe5369\`). Re-enable only after:

- #367: owner-approved licensing and exact package distribution scope;
- #586: written clearance for any NVIDIA firmware (or no firmware payload);
- #39 / #534: verified channel inputs and owner-controlled WSM authentication;
- #750 / #757: substitute endpoint, trust, publication and key-custody design.

Cuirass is a build coordinator, not a substitute server. A successful ephemeral
build is not a release or permission to distribute its store closure.
