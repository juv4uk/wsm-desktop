# Feasibility: QEMU CXL Type 3 та Linux cxl_test

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **CI feasibility experiment**
- Пов'язана задача: [#94 — QEMU CXL та kernel cxl_test](https://github.com/juv4uk/wsm-desktop/issues/94)
- Пов'язані контракти: [#18 — topology relationships](https://github.com/juv4uk/wsm-desktop/pull/42), [#81 — DOE/SPDM та CXL RAS](https://github.com/juv4uk/wsm-desktop/issues/81), [#66 — QEMU guest runtime](https://github.com/juv4uk/wsm-desktop/issues/66)
- Host probe: `scripts/ci_probe_qemu_cxl.py`
- Guest probe: `scripts/ci_qemu_cxl_guest.py`
- Workflow: `.github/workflows/qemu-cxl-feasibility.yml`

## Різні рівні доказу

QEMU CXL emulation, Linux `cxl_test`, KUnit та synthetic sysfs fixtures не є взаємозамінними:

- **QEMU qdev/device-tree probe** доводить, що конкретна QEMU build створила Host Bridge, Root Port і Type 3 device objects. Сам по собі не доводить Linux guest discovery.
- **QEMU + Linux guest CXL drivers** перевіряє, що точне guest kernel виявляє CXL objects через ACPI/PCI і створює report-local sysfs devices/links.
- **Linux `cxl_test`** з `tools/testing/cxl/` емулює host bridges, switches, memory devices і mailboxes для інтеграційних тестів CXL driver stack та sysfs ABI; ndctl запускає його suites через `meson test -C build --suite cxl`.
- **KUnit** тестує внутрішню логіку CXL driver, але не створює topology.
- **Synthetic sysfs fixtures** дешеві й детерміновані для parser semantics, але не підтверджують поведінку реального kernel.

## Upstream evidence

Офіційна документація QEMU описує CXL 2.0+ Host Bridges, Root Ports, switches і Type 3 volatile/persistent memory devices, CFMW та CEDT. QEMU не моделює electrical/protocol link behavior і не доводить реальну memory reliability.

Джерело: [QEMU CXL devices](https://www.qemu.org/docs/master/system/devices/cxl.html).

Linux kernel testing docs описують `cxl_test`, побудову `make M=tools/testing/cxl` і запуск ndctl CXL suite. Це сильніший driver-stack test, але окрема kernel/ndctl lane з більшим часом build/run.

Джерело: [Linux CXL testing](https://docs.kernel.org/next/driver-api/cxl/testing.html).

Корисний upstream reuse candidate: [pmem/ndctl-test-runner](https://github.com/pmem/ndctl-test-runner). Це GitHub Actions workflow, який збирає Linux kernel, завантажує його в QEMU та запускає ndctl CXL/NVDIMM/DAX suites на GitHub-hosted infrastructure без спеціального обладнання; має scheduled runs по CXL next/fixes та linux-next. Його варто повторно використати/форкнути для важчого kernel-driver lane, а не писати власний kernel builder.

Джерела: [ndctl test runner README](https://github.com/pmem/ndctl-test-runner), [ndctl releases](https://github.com/pmem/ndctl/releases).

## Runner environment snapshot

Перший реальний QEMU device-tree probe на GitHub-hosted Ubuntu 24.04 виявив:
- QEMU 8.2.2 (`1:8.2.2+ds-0ubuntu1.18`);
- kernel `7.0.0-1017-azure`;
- `CONFIG_CXL_BUS=m`, `CONFIG_CXL_PCI=m`, `CONFIG_CXL_ACPI=m`, `CONFIG_CXL_MEM=m`, `CONFIG_CXL_PORT=m`, `CONFIG_CXL_REGION=y`;
- на host є модулі `cxl_core`, `cxl_pci`, `cxl_acpi`, `cxl_mem`, `cxl_port`, `cxl_pmem` як module artifacts;
- QEMU створив synthetic IDs `cxl.1`, `root_port0`, `cxl-vmem0`.

Це доводить наявність потрібного runner kernel/module material для наступного guest-stage, але не те, що host driver працює: жоден host CXL module не завантажується.

## Disposable Linux guest

Другий workflow boot-ить runner kernel з тимчасовим initramfs:
1. Host читає `modprobe --show-depends`, копіює лише CXL module dependency set у scratch initramfs, обмежує кожен archive та aggregate size і розпаковує його.
2. QEMU TCG завантажує kernel/initramfs з volatile RAM-backed Type 3 CXL device.
3. Лише **guest kernel** завантажує CXL modules, монтує read-only `/proc` та `/sys` і читає `/sys/bus/cxl/devices`.
4. У serial виходять лише report-local назви типів CXL device і типізовані edges. BDF, serial numbers, HPA/DPA coordinates і raw poison data не виводяться.
5. Для позитивного результату потрібен принаймні один `mem*` Type 3 memdev і один `root*`/ `port*` object; лише QEMU qdev tree без guest sysfs discovery не достатній.

Isolation: TCG, 1 vCPU, 1 GiB initial guest RAM, volatile 256 MiB Type 3 backend, no disk, no NIC, no host passthrough, no EFI variable store, no shared folders. Host module loader використовується тільки з `--show-depends`; modules are loaded inside guest, not host. Serial/stderr share the bounded reader from #64 (1 MiB / 256 KiB).

No CXL region/namespace is created. No decoder/region configuration, poison list, scrub, ECS, sanitize, repair, erase, firmware update or real memory operation is run.

## Future `cxl_test` lane

Якщо QEMU guest-stage успішний, окрема наступна робота може повторно використати `pmem/ndctl-test-runner` для kernel `cxl_test` suites, pinned kernel/ndctl commits and config. Це не слід додавати до кожного базового PR; це окрема scheduled/manual integration lane через вищу вартість kernel build.

Ці експерименти доводять лише synthetic CXL enumeration і software driver behavior. Вони не сертифікують фізичне CXL обладнання, link integrity, memory performance/reliability або firmware security.
