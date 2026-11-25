# WSM Desktop

> Independent desktop Linux distribution built on GNU Guix System.

**WSM Desktop** is an independent project to build a comfortable, reproducible desktop Linux system with a graphical installer based on Calamares and a declarative system configuration based on GNU Guix.

The project is in **pre-alpha**. There is no supported installation image yet. The repository currently defines the project architecture and development foundations; it must not be used to install or modify a real system.

## Project status

- [x] Project identity and scope
- [x] Initial architecture and licensing policy
- [ ] Reproducible Guix channel snapshot
- [ ] Minimal target system validated in a virtual machine
- [ ] Calamares packaging and live-environment feasibility check
- [ ] Guix deployment backend prototype
- [ ] End-to-end installation in QEMU
- [ ] Hardware compatibility testing
- [ ] First public preview image

See [the roadmap](docs/ROADMAP.md) for milestones and acceptance criteria.

## Technology

| Component | Responsibility |
| --- | --- |
| GNU Guix System | Declarative operating-system configuration, package management, services, generations, and system deployment |
| Calamares | Graphical installation workflow and user-facing installer |
| WSM Guix deployment adapter | Project-owned integration between Calamares and Guix System |
| Nonguix (optional) | Separately selected nonfree firmware, drivers, or other packages when required |
| QEMU | Safe virtual-machine testing before physical hardware installation |

WSM Desktop is not a fork of GNU Guix, Nonguix, or Calamares. We aim to reuse upstream projects and contribute fixes upstream whenever practical.

## Principles

1. **Usable by default.** The goal is a comfortable desktop operating system, not a command-line-only demonstration.
2. **Reproducible by design.** Pin channel revisions for release builds, record build inputs, and make system configuration reviewable.
3. **Free software first.** The default profile must not require Nonguix or nonfree components.
4. **Explicit compatibility choices.** Optional nonfree components must be clearly identified, justified by hardware needs, and selected knowingly.
5. **No hidden trust.** Verify channel introductions, substitute signing keys, source revisions, and licenses. Never silently add a binary cache or signing key.
6. **Fail safely.** The installer must validate the target plan before writing to disks. Incomplete or ambiguous plans must stop without making changes.
7. **Upstream respect.** Preserve upstream notices, licenses, trademarks, and community policies.

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
       WSM Guix deployment adapter
              |
              v
       generated Guix System configuration
              |
              v
       guix system init
              |
              v
       installed WSM Desktop system
```

This is a design target, not a working installer yet.

### Important integration boundary

Guix System owns the declarative target configuration and system deployment. In particular, the generated Guix configuration must describe the bootloader and target file systems. We must not let a stock Calamares bootloader job and `guix system init` both attempt to install or configure the bootloader.

Likewise, Calamares' generic user-creation step must not be assumed to create a correct declarative Guix `user-account`. User creation, password handling, file-system mapping, and bootloader setup need an explicit WSM integration design.

## Profiles

The project intends to provide two clearly separated installation choices:

- **WSM Free** — uses the official Guix channel and free-software components only.
- **WSM Compatibility** — may add explicitly selected Nonguix components when needed for hardware support.

The compatibility profile is optional. Nonguix is an independent community channel and is not endorsed by the GNU Guix project. Review its own warnings and package licenses before enabling or redistributing its contents.

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

## Licensing and project identity

Original source code in this repository is licensed under **GPL-3.0-or-later**. Project documentation is licensed under **CC-BY-SA-4.0**. See [LICENSE](LICENSE), [LICENSES/CC-BY-SA-4.0.txt](LICENSES/CC-BY-SA-4.0.txt), and [docs/LICENSING.md](docs/LICENSING.md).

GNU, GNU Guix, Nonguix, and Calamares are independent projects. Their names and marks identify their respective projects and are not claims of affiliation or endorsement. WSM Desktop is not an official GNU, Guix, Nonguix, or Calamares distribution.

---

**Project stage:** pre-alpha / architecture and bring-up.  
**Current guarantee:** no production installation support; no supported ISO; no validated hardware support list.
