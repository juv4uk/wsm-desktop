# WSM Desktop

> English translation. The canonical document is [README.md](README.md);
> in any disagreement the Ukrainian text wins.

> Hardware-oriented desktop Linux based on GNU Guix System; Nix/NixOS is deferred research.

**WSM Desktop** is an independent, hardware-oriented project to build a comfortable, reproducible desktop Linux system with a graphical installer. Its central purpose is to select and integrate proven upstream kernels, drivers, firmware and hardware tools for concrete hardware configurations, while making compatibility evidence understandable before installation. GNU Guix System is the selected system backend for the first release; Nix/NixOS is deferred, not rejected. The project does not merge their package stores or system managers.

## Try it now

The working component available today is the hardware collector. Inventory uses sysfs and procfs; the collector also reads local kernel-module indexes from `/lib/modules/<kernel>/` and, when available, bounded kernel-log diagnostics through fixed read-only `journalctl -k -b` or `dmesg` commands. It does not modify block devices, partition tables, filesystems, or system state. By default, the report goes to stdout; `--output PATH` writes only the JSON report to the explicitly selected file.

```console
$ git clone https://github.com/juv4uk/wsm-desktop.git
$ cd wsm-desktop
$ python3 -m wsm_hwcheck --compact            # JSON report to stdout
$ python3 -m wsm_hwcheck --output hw.json     # or to a file
```

The report is validated against a versioned schema and marks missing evidence as `unknown` instead of guessing:

```console
$ python3 -m venv .venv
$ . .venv/bin/activate
$ python -m pip install 'jsonschema[format]==4.26.0'
$ python -m wsm_install --preflight --report hw.json --backend guix --dry-run
```

The `wsm_install` command prints a diagnostic plan for this machine. It remains a draft by design: it is not an installation plan until a target disk is selected and required device roles are confirmed.

The project is in **pre-alpha**. There is no supported installation image yet. The repository currently defines the project architecture and development foundations; it must not be used to install or modify a real system.

## Release 0.1.0-rc1

The first public pre-release is [WSM Desktop 0.1.0-rc1 — Hardware Preview](https://github.com/juv4uk/wsm-desktop/releases/tag/0.1.0-rc1). It ships the read-only tools and a reproducible source bundle, not an installation image: there is no supported installation in it.

Verify what you downloaded:

```sh
sha256sum -c SHA256SUMS
python3 -c 'import json; d=json.load(open("release-manifest.json")); n="wsm-desktop-0.1.0-rc1-source.tar.gz"; print(d["source_commit"], d["artifacts"][n]["sha256"])'
```

The tarball is built with `git archive HEAD | gzip -n -9` at `mtime=0`, so the same commit yields the same bytes. Full scope, known limitations and how to report back are in [RELEASE-NOTES.md](RELEASE-NOTES.md).

## Project status

- [x] Project identity and scope
- [x] Initial architecture and licensing policy
- [ ] Optional Nix/NixOS research (not blocking the first Guix preview)
- [x] Select the first WSM system backend (GNU Guix; Nix deferred, see ADR 0004)
- [ ] Installer frontend selection and live-environment feasibility
- [x] Guix handoff plan preparation (dry-run only; no execution or target-disk writes)
- [ ] End-to-end installation in QEMU
- [ ] Hardware compatibility testing
- [ ] First public preview image

See [the roadmap](docs/ROADMAP.md) for milestones and acceptance criteria. The installer frontend is being evaluated in [issue #10](https://github.com/juv4uk/wsm-desktop/issues/10); Calamares is not a locked dependency. The hardware-first/upstream-first direction is explored through [the hardware preflight](docs/hardware/HWCHECK.md) and the [upstream tooling assessment](docs/hardware/UPSTREAM-TOOLING.md). [ADR 0004](docs/decisions/0004-nix-guix-backend-strategy.md) records the ratified decision: GNU Guix System first, Nix/NixOS deferred. The current Calamares 3.4.2 assessment is in [docs/CALAMARES-FEASIBILITY.md](docs/CALAMARES-FEASIBILITY.md).

## Technology

| Component | Responsibility |
| --- | --- |
| GNU Guix System | Selected backend for the first release: declarative operating-system configuration and package management |
| Nix / NixOS | Deferred backend; research only, not part of the first preview image |
| Installer frontend | Under evaluation; Calamares is one candidate, not a selected dependency |
| WSM backend adapter | Project-owned integration between the selected frontend and the GNU Guix System backend |
| Nonguix (optional) | Separately selected nonfree firmware, drivers, or other packages when required |
| QEMU | Safe virtual-machine testing before physical hardware installation |

WSM Desktop is not a fork of GNU Guix, Nonguix, or Calamares. We aim to reuse upstream projects and contribute fixes upstream whenever practical.

## Principles

1. **Usable by default.** The goal is a comfortable desktop operating system, not a command-line-only demonstration.
2. **Hardware-first.** Compatibility is a first-class system concern. WSM inventories concrete hardware and combinations, records evidence per device and function, and reports unknowns honestly instead of advertising unsupported compatibility.
3. **Upstream-first reuse.** Prefer maintained upstream kernels, drivers, firmware, tools, packages and trusted build artifacts. Do not rebuild or reimplement what already works well. Build, patch or fork only when a measured compatibility or integration need justifies it; prefer contributing general fixes upstream.
4. **Reproducible by design.** Pin channel and source revisions for release builds, record build inputs, and make system configuration reviewable.
5. **Free software first.** The default profile must not require Nonguix or nonfree components.
6. **Explicit compatibility choices.** Optional nonfree components must be clearly identified, justified by hardware needs, and selected knowingly.
7. **No hidden trust.** Verify source provenance, licenses, signatures and substitute trust. Never silently add a binary cache or signing key.
8. **Fail safely.** The installer must validate the hardware report and target plan before writing to disks. Unknown results must be explained; unsafe or impossible installation paths must stop before disk changes.
9. **Upstream respect.** Preserve upstream notices, licenses, trademarks, security processes and community policies.

## Installation concept

The intended installation flow is:

```text
Live environment
    |
    v
Selected WSM installer frontend (not selected yet)
    |
    +--> frontend-native pages for supported tasks
    |
    +--> WSM-specific configuration and preflight
              |
              v
       WSM backend adapter (wsm_install/backend_guix.py)
              |
              +--> GNU Guix deployment path (selected, ADR 0004)
              |
              +--> Nix/NixOS (deferred research; not implemented)
              |
              v
       installed WSM Desktop system
```

This is a design target, not a working installer yet. The Guix adapter prepares an `operating-system` declaration from a confirmed plan and returns allow-listed argv; it does not execute the command or write to a disk. Nix/NixOS is deferred and is not part of the first installation path.

### Backend ownership

The first WSM preview supports GNU Guix System only. Any future Nix/NixOS edition must have its own independent deployment implementation; the project will never let two backends manage the same root filesystem, bootloader, or service manager.

For the **Guix backend**, the generated Guix configuration owns the target file systems, user accounts, services, and bootloader. We must not let a stock Calamares bootloader job and `guix system init` both attempt to install or configure the bootloader. If Calamares is selected, its generic user-creation step must not be assumed to create a correct declarative Guix `user-account`.

The Nix/NixOS backend needs its own deployment design; it is not implemented by reusing Guix commands.

## Profiles

The project intends to provide two clearly separated software-policy choices:

- **WSM Free** — only components that meet the project's free-software policy.
- **WSM Compatibility** — explicitly selected components outside that policy, with their licenses and redistribution terms disclosed.

These are WSM policy labels, not a claim that both profiles are already implemented in Guix. Their package sources and exact behavior must be defined separately for each backend. On the Guix path, Nonguix may be considered as an optional independent channel; it is not endorsed by the GNU Guix project.

## Repository map

```text
channels/       Guix channel input examples
docs/           Architecture, decisions, ethics, and development guidance
installer/      Calamares configuration and WSM integration design
systems/        Guix System configuration examples
tests/          Tests for project-owned tooling
wsm/            Future project Guix channel modules
```

Directories will gain implementation as the relevant design decisions and tests are completed.

## Upstream documentation

See [docs/UPSTREAMS.md](docs/UPSTREAMS.md) for the official Guix, Calamares, and Nonguix references used by this project.

## Development

Start with [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). The initial workflow is to inspect and validate the Guix configuration in a virtual machine. Do not test an unfinished installer against a disk containing data you need.

## Current architecture status

The backend decision is closed. [ADR 0004](docs/decisions/0004-nix-guix-backend-strategy.md) was ratified on 2026-11-25: GNU Guix System is the first and only supported backend, consistent with the already accepted [ADR 0001](docs/decisions/0001-guix-as-system-foundation.md). The Nix experiment is kept as research and is off the critical path. Issue [#2](https://github.com/juv4uk/wsm-desktop/issues/2) tracks the Guix-first architecture decision and the deferral of Nix/NixOS; installer frontend selection remains a separate issue [#10](https://github.com/juv4uk/wsm-desktop/issues/10). Each installed system must have one authoritative backend; the project does not combine Nix and Guix stores or activation systems.

## Licensing and project identity

All work created for WSM Desktop in this repository — code, configuration, tests and documentation — is released under the **VOLNIST** licence. See [LICENSE](LICENSE) and [docs/LICENSING.md](docs/LICENSING.md).

Third-party components — GNU Guix, Calamares, Nonguix, Linux, drivers, firmware — keep their own licences. This licence does not change them and does not relicense them.

---

**Project stage:** pre-alpha / GNU Guix System integration.  
**Current guarantee:** no production installation support; no supported ISO; no validated hardware support list.