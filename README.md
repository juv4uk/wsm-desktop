# WSM Desktop

> Hardware-oriented desktop Linux project exploring Nix and GNU Guix as declarative system foundations.

**WSM Desktop** is an independent, hardware-oriented project to build a comfortable, reproducible desktop Linux system with a graphical installer. Its central purpose is to select and integrate proven upstream kernels, drivers, firmware and hardware tools for concrete hardware configurations, while making compatibility evidence understandable before installation. Its architecture is evaluating Nix and GNU Guix as separate native system backends; no decision has been made to merge their package stores or system managers.

The project is in **pre-alpha**. There is no supported installation image yet. The repository currently defines the project architecture and development foundations; it must not be used to install or modify a real system.

## Project status

- [x] Project identity and scope
- [x] Initial architecture and licensing policy
- [ ] Comparative Nix and Guix backend evaluation
- [ ] Select and validate the first WSM system backend
- [ ] Calamares packaging and live-environment feasibility check
- [ ] Backend-specific deployment adapter prototype
- [ ] End-to-end installation in QEMU
- [ ] Hardware compatibility testing
- [ ] First public preview image

See [the roadmap](docs/ROADMAP.md) for milestones and acceptance criteria. The hardware-first/upstream-first direction is explored through [the hardware preflight](docs/hardware/HWCHECK.md) and the [upstream tooling assessment](docs/hardware/UPSTREAM-TOOLING.md). The proposed dual-backend direction is recorded in [ADR 0004](docs/decisions/0004-nix-guix-backend-strategy.md) and is not yet ratified. The current Calamares 3.4.2 assessment is in [docs/CALAMARES-FEASIBILITY.md](docs/CALAMARES-FEASIBILITY.md).

## Technology

| Component | Responsibility |
| --- | --- |
| Nix / NixOS | Candidate native backend for declarative system configuration, package builds, and activation |
| GNU Guix System | Candidate native backend for declarative operating-system configuration and package management |
| Calamares | Intended graphical installation workflow and user-facing installer |
| WSM backend adapter | Project-owned integration between Calamares and one selected system backend |
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
Calamares user interface
    |
    +--> existing Calamares pages for supported tasks
    |
    +--> WSM-specific configuration and preflight
              |
              v
       WSM backend adapter
              |
              +--> Nix/NixOS deployment path
              |
              +--> GNU Guix deployment path
              |
              v
       installed WSM Desktop system
```

This is a design target, not a working installer yet. Nix and Guix deployment must remain separate backend implementations until comparative tests justify a supported release model.

### Backend ownership

Each installed WSM system must have exactly one backend responsible for system configuration and activation. The Nix/NixOS and Guix deployment paths are separate and must not both attempt to manage the same root filesystem, bootloader, or service manager.

For the **Guix backend**, the generated Guix configuration owns the target file systems, user accounts, services, and bootloader. We must not let a stock Calamares bootloader job and `guix system init` both attempt to install or configure the bootloader. Calamares' generic user-creation step must not be assumed to create a correct declarative Guix `user-account`.

The Nix/NixOS backend needs its own deployment design; it is not implemented by reusing Guix commands.

## Profiles

The project intends to provide two clearly separated software-policy choices:

- **WSM Free** — only components that meet the project's free-software policy.
- **WSM Compatibility** — explicitly selected components outside that policy, with their licenses and redistribution terms disclosed.

These are WSM policy labels, not a claim that both backends already implement the profiles. Their package sources and exact behavior must be defined separately for each backend. On the Guix path, Nonguix may be considered as an optional independent channel; it is not endorsed by the GNU Guix project.

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

The initial Guix configuration remains a useful prototype. A Nix-based experiment is also underway. Issue [#2](https://github.com/juv4uk/wsm-desktop/issues/2) tracks the comparison. Each installed system must have one authoritative backend; the project does not combine Nix and Guix stores or activation systems.

## Licensing and project identity

Original source code in this repository is licensed under **GPL-3.0-or-later**. Project documentation is licensed under **CC-BY-SA-4.0**. See [LICENSE](LICENSE), [LICENSES/CC-BY-SA-4.0.txt](LICENSES/CC-BY-SA-4.0.txt), and [docs/LICENSING.md](docs/LICENSING.md).

GNU, GNU Guix, Nonguix, and Calamares are independent projects. Their names and marks identify their respective projects and are not claims of affiliation or endorsement. WSM Desktop is not an official GNU, Guix, Nonguix, or Calamares distribution.

---

**Project stage:** pre-alpha / backend architecture evaluation.  
**Current guarantee:** no production installation support; no supported ISO; no validated hardware support list.
