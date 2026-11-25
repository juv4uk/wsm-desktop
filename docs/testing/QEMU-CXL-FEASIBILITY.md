# Feasibility: QEMU CXL Type 3 та Linux cxl_test

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **CI feasibility experiment**
- Пов'язана задача: [#94 — QEMU CXL та kernel cxl_test](https://github.com/juv4uk/wsm-desktop/issues/94)
- Пов'язані контракти: [#18 — topology relationships](https://github.com/juv4uk/wsm-desktop/pull/42), [#81 — DOE/SPDM та CXL RAS](https://github.com/juv4uk/wsm-desktop/issues/81), [#66 — QEMU guest runtime](https://github.com/juv4uk/wsm-desktop/issues/66)
- CI script: `scripts/ci_probe_qemu_cxl.py`
- Workflow: `.github/workflows/qemu-cxl-feasibility.yml`

## Висновок на старті

QEMU CXL emulation і Linux `cxl_test` не є взаємозамінними:

- **QEMU CXL Type 3** перевіряє, що QEMU може створити emulated PCI/CXL hardware topology, а після завантаження відповідного guest kernel — що Linux її виявляє через CXL driver stack і sysfs.
- **Linux `cxl_test`** — окремий kernel test framework із модулів `tools/testing/cxl/`, який емулює topology на рівні CXL driver stack. Він призначений для sysfs/topology/region/decoder поведінки та запускається разом із ndctl test suite.
- **Synthetic sysfs fixtures** дешеві й детерміновані для parser/semantic tests, але не доводять, що реальне ядро створює такі links/attributes.
- **KUnit** підходить для ізольованої внутрішньої логіки CXL driver, але не замінює topology integration tests через `cxl_test`.

Жоден із цих режимів не є доказом фізичної CXL-сумісності, якості лінії, коректності реального memory controller, firmware або memory integrity.

## Upstream evidence

### QEMU

Офіційна документація QEMU фокусується на CXL 2.0 та новіших revision і описує Type 3 volatile/persistent memory devices, host bridges, root ports, switches, HDM decoders, CEDT/CFMW, DOE, IDE та AER. QEMU не моделює electrical/protocol link behavior; cache/coherency operations поза загальним emulation scope.

Однопристроєвий volatile Type 3 topology в official QEMU docs має такі елементи:

- `q35,cxl=on` — CXL-capable machine;
- `pxb-cxl` — CXL host bridge;
- `cxl-rp` — root port;
- `cxl-type3` + `memory-backend-ram` — volatile Type 3 device backed by anonymous QEMU RAM;
- CXL fixed memory window — `cxl-fmw`.

Мінімальна команда відтворення з CI probe використовує ті самі основні QEMU objects, але не завантажує гостьове ядро: CPU залишається paused через `-S`, відсутні диски, NIC, shared folders і passthrough. Успіх цього кроку доводить лише те, що конкретна QEMU build змогла створити зазначений device tree.

Джерело: [QEMU CXL device documentation](https://www.qemu.org/docs/master/system/devices/cxl.html).

### Linux `cxl_test` та KUnit

Linux kernel docs поділяють ці шляхи:

- `cxl_test` з `tools/testing/cxl/` emulates host bridges, switches, memory devices і mailboxes. Документація пропонує `make M=tools/testing/cxl`, після чого CXL-тести ndctl запускаються через `meson test -C build --suite cxl`.
- KUnit запускає self-contained CXL logic tests у тестовому kernel; він не створює CXL topology. Для нього використовується `./tools/testing/kunit/kunit.py run --kunitconfig=drivers/cxl`; за потреби можна вказати `--arch=x86_64` для QEMU.

Отже, `cxl_test` більше підходить для інтеграційних перевірок sysfs/driver topology, KUnit — для внутрішніх алгоритмів, а QEMU — для перевірки firmware-described PCI/CXL discovery в гостьовому kernel.

Джерела: [Linux CXL testing](https://docs.kernel.org/next/driver-api/cxl/testing.html), [ndctl CXL test build requirements](https://github.com/pmem/ndctl#cxl-test).

### Версії та повторюваність

У першому CI run фіксуються фактичні версії runner kernel і QEMU package. Для відтворюваної наступної guest-lane потрібно буде pin-ити:
- Linux kernel source commit/config, якщо наявні runner modules не дають потрібного CXL support;
- QEMU package version;
- ndctl version/commit і test suite;
- конкретні Kconfig values та module artifacts.

Не використовувати рухомий `master` як release pin. Не вважати GitHub-hosted runner kernel конфігураційно однаковим між різними датами.

## Матриця: що доводить кожен метод

| Метод | Що реально тестує | Чого не доводить | Рекомендована роль |
| --- | --- | --- | --- |
| QEMU Type 3 device-tree probe | QEMU build приймає CXL machine/device properties і створює синтетичний host bridge/root-port/Type 3 object graph | Linux CXL driver discovery, sysfs relationships, memory region activation, physical CXL behavior | Швидкий CI capability check |
| QEMU + Linux guest CXL drivers | ACPI CEDT/CFMWS + PCI/CXL discovery у точному guest kernel; report-local sysfs links і attributes | Physical firmware, electrical link, real device reliability, production memory performance | Один optional end-to-end VM test |
| Linux `cxl_test` + ndctl suite | Kernel CXL driver stack на mock topology; port/endpoint enumeration, region assembly, decoder behavior, sysfs ABI | QEMU firmware handoff, physical CXL hardware, electrical/link behavior | Dedicated kernel/ndctl integration lane |
| KUnit CXL suites | Ізольовані CXL algorithms, mailbox/parser/address-translation logic | Live topology, sysfs relationship discovery | Kernel unit tests |
| Synthetic sysfs fixtures | Parser behavior, unknown/not-collected semantics, topology graph validation/privacy rules | Реальний kernel behavior чи ABI availability | Fast Python tests |

## Read-only evidence policy

Для майбутнього optional CXL provider WSM може читати лише вже експоновані sysfs facts, наприклад:
- тип і наявність CXL bus/device/port об'єктів;
- report-local links, які kernel реально створив між host bridge, port, endpoint і memdev;
- read-only capacity/NUMA attributes, якщо вони присутні.

Не запускати `cxl create-region`, `cxl destroy-region`, decoder commit, poison-list trigger, scrub/ECS reset, sanitize, repair, erase, firmware update або інші operation-triggering commands. Не читати й не експортувати serial number, raw HPA/DPA addresses чи raw poison records. Наявність пристрою та sysfs topology — це enumeration evidence, не функціональний pass.

CXL security/reliability залишаються окремою панеллю від driver binding, firmware availability та функціональної сумісності (див. #81/#84).

## Поточний CI experiment

`qemu-cxl-feasibility.yml`:
1. встановлює стандартний QEMU package на Ubuntu 24.04 runner;
2. читає конфігурацію runner kernel і шукає доступні CXL modules без їх завантаження;
3. запускає QEMU з paused CPU та synthetic volatile Type 3 device tree;
4. перевіряє, що QEMU створив expected qdev IDs;
5. не прикріплює host disk, NIC, shared folder або physical device.

Цей початковий probe навмисно не створює/не монтує гостьові namespaces і не завантажує kernel modules. Його результат дає підставу для наступного рішення: чи продовжувати з QEMU guest kernel, чи використовувати dedicated `cxl_test`/KUnit lane або синтетичні sysfs fixtures. Позитивний QEMU result не означає, що Linux guest CXL driver підтримка доступна; ці два результати записуються окремо.
