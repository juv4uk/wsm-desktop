# QEMU CXL та cxl_test: результати feasibility

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: підтверджений інженерний експеримент; не hardware compatibility certification
- Дата: 2026-11-25
- Пов'язана задача: [#94 — QEMU CXL та kernel cxl_test](https://github.com/juv4uk/wsm-desktop/issues/94)
- Реалізація: [#95 — QEMU Type 3 model probe](https://github.com/juv4uk/wsm-desktop/pull/95), [#104 — Linux guest sysfs enumeration](https://github.com/juv4uk/wsm-desktop/pull/104)

## Рішення

Для WSM доцільно використовувати **три окремі рівні тестування**, а не один універсальний CXL тест:

1. **Synthetic sysfs fixtures** — швидка обов'язкова перевірка parser-а та typed topology relationships у звичайному CI.
2. **QEMU Type 3 Linux guest** — необов'язковий end-to-end smoke для реального kernel driver discovery та read-only sysfs enumeration.
3. **Linux `cxl_test` + ndctl CXL tests** — окремий розширений test environment для поведінки driver stack на складнішій емульованій топології, коли WSM почне споживати ці відносини або підтримувати decoder/region workflow.

Жоден із цих рівнів не є доказом сумісності фізичного CXL пристрою. CXL не повинен ставати обов'язковим компонентом базового x86_64 desktop preflight.

## QEMU model: що доведено

### Model-only probe (#95)

QEMU запускали з одним synthetic volatile Type 3 пристроєм:

- machine: `q35,cxl=on`;
- accelerator: TCG;
- host bridge: `pxb-cxl`;
- root port: `cxl-rp`;
- endpoint: `cxl-type3`;
- memory backend: 256 MiB volatile RAM;
- CXL fixed memory window задавався лише як частина моделі QEMU;
- QMP `info qtree` підтвердив створений об'єкт `cxl-vmem0` із типом `cxl-type3`.

Фактичне підтвердження: [CXL QEMU model workflow](https://github.com/juv4uk/wsm-desktop/actions/workflows/cxl-qemu-feasibility.yml) у PR #95. Успішний run доводить, що встановлений QEMU binary прийняв конфігурацію та створив саме Type 3 object; перевірка одного лише `-device help` або очікування timeout такого доказу не дають.

### Linux guest sysfs enumeration (#104)

Окремо завантажено точний runner kernel у disposable QEMU TCG guest з одним synthetic CXL Type 3 volatile device. Вісім kernel modules із залежностями розпаковано до тимчасового initramfs і завантажено **тільки всередині guest**.

Фактичний успішний запуск:

- GitHub Actions run: [#45688904621](https://github.com/juv4uk/wsm-desktop/actions/runs/45688904621);
- QEMU: `8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`;
- guest kernel: `7.0.0-1017-azure`;
- CXL module dependency closure: 8 модулів, 1,162,544 байти у розпакованому вигляді;
- `guest_sysfs_enumeration=observed`;
- `cxl_memdev_count=1`;
- `cxl_region_created=false`.

У `/sys/bus/cxl/devices` виявлено 11 імен вузлів:

```text
decoder0.0
decoder1.0
decoder2.0
decoder2.1
decoder2.2
decoder2.3
endpoint2
mem0
nvdimm-bridge0
port1
root0
```

Read-only `devtype` observations:

| Вузол | Повідомлений `devtype` |
| --- | --- |
| `root0` | `cxl_port` |
| `port1` | `cxl_port` |
| `endpoint2` | `cxl_port` |
| `decoder0.0` | `cxl_decoder_root` |
| `decoder1.0` | `cxl_decoder_switch` |
| `decoder2.0`–`decoder2.3` | `cxl_decoder_endpoint` |
| `nvdimm-bridge0` | `cxl_nvdimm_bridge` |
| `mem0` | node name і memdev counter; `devtype` для нього цей probe не збирав |

Результат підтверджує, що ACPI CEDT/ACPI0017, QEMU Type 3 model і Linux CXL drivers можуть разом породити гостьове дерево root/ports/endpoint/decoders та один memdev.

**Не виводити фізичну пару `endpoint2 ↔ mem0` лише з того, що обидва вузли існують.** Linux CXL driver documentation прямо зазначає, що sysfs не зберігає відношення між endpoint і memdev фізичного пристрою. WSM має фіксувати лише явно представлені symlink/parent/child edges; коли зв'язок не експонується — залишати його `unknown/not-exposed`, а не реконструювати за індексами чи порядком enumeration.

## Порівняння тестових рівнів

| Варіант | Що перевіряє | Чого не доводить | Рекомендоване використання |
| --- | --- | --- | --- |
| Synthetic sysfs fixtures | Parser, нормалізацію node names, `devtype`, symlink graph, missing/permission-denied states, privacy filtering | Реальне створення kernel kobjects, driver binding, ACPI/PCI enumeration | Швидкі обов'язкові unit tests; детерміновані edge cases |
| QEMU Type 3 guest | Реальна поведінка конкретного гостьового kernel/driver stack на емульованій ACPI/PCI/CXL topology; фактичні sysfs nodes | Cache coherency, реальна фізична пам'ять, firmware конкретного vendor, фізична сумісність, production reliability | Необов'язковий CI smoke після змін topology/evidence parser-а |
| Linux `cxl_test` + ndctl | Driver-stack поведінку на емульованих host bridges, switches, memory devices і mailboxes; live topology/sysfs; ширші сценарії портів/decoder/region | Повну фізичну платформу, реальну firmware, electrical/link characteristics, cache-coherency hardware | Розширені kernel/driver developer tests; запускати окремо, не в базовому installer path |
| Physical CXL system | Реальний BIOS/firmware, фізичні links, memory device та platform behavior | Автоматично — усі інші платформи чи конфігурації | Окремий hardware lab evidence із повним provenance |

### QEMU limitations

Офіційна QEMU документація описує Type 3 memory devices, CXL 2.0+ topology, host bridges, ports, switches, DOE/AER/IDE-related PCIe interfaces та volatile/persistent memory backends. Водночас вона прямо зазначає, що QEMU **не емулює cache-coherency protocol**. Отже, QEMU не може сертифікувати CXL.cache, реальне coherent memory sharing або фізичні властивості fabric.

У поточному WSM smoke ми навмисно не створювали CXL region і не виконували memory allocation через CXL. Видима наявність decoder nodes не означає, що decoder-и committed або регіон активовано.

### Linux `cxl_test`

Upstream Linux описує `cxl_test` як framework, що емулює host bridges, switches, memory devices та mailboxes для тестування CXL driver stack без фізичного обладнання. Документація відрізняє його від KUnit:

- `cxl_test` потрібен для поведінки, залежної від live topology і sysfs ABI;
- KUnit — для ізольованої логіки без повної topology;
- upstream build entry point для test modules: `make M=tools/testing/cxl`;
- integration tests підтримуються в ndctl repository у `test/cxl-<name>.sh`.

Це кращий кандидат для майбутнього розширеного тестування driver interaction, ніж розширювати preflight скрипт прямими control operations.

## Архітектура WSM: наступна робота

1. Додати synthetic sysfs fixtures для `root0 → port → endpoint`, decoder type та відсутніх/недоступних attributes.
2. Перевіряти тільки реальні sysfs symlinks/parent references. Не вигадувати endpoint↔memdev relation: upstream прямо попереджає, що вона не експонується.
3. Розділити стани: `observed`, `not-exposed`, `not-enumerated`, `permission-denied`, `not-applicable`; відсутність вузла не дорівнює доведеній несумісності.
4. Залишити QEMU guest scenario необов'язковим CI job, а `cxl_test` — окремою розширеною задачею, коли з'явиться конкретна поведінка WSM, яку треба тестувати.
5. Не змінювати report schema та core collector, доки власники #5/#6/#16/#18 не погодять typed topology contract.

## Безпекові межі

Поточний guest сценарій:

- не має віртуального диска, NIC чи host passthrough;
- працює під QEMU TCG;
- копіює kernel image і module files тільки в тимчасовий workspace;
- завантажує CXL modules тільки всередині guest;
- монтує guest `/sys` та `/proc` read-only;
- не створює CXL region і не програмує decoder-и;
- не читає serial numbers, poison lists, HPA/DPA coordinates чи firmware payloads;
- не виконує scrub, ECS reset, memory repair, sanitize, erase або firmware update;
- не змінює host sysfs, host module state чи фізичні пристрої.

## Джерела

- QEMU, [Compute Express Link (CXL) devices](https://www.qemu.org/docs/master/system/devices/cxl.html) — модель Type 3, приклади топології та обмеження cache-coherency emulation.
- Linux kernel, [CXL driver operation](https://www.kernel.org/doc/html/latest/driver-api/cxl/linux/cxl-driver.html) — роль root/ports/endpoints/memdev, ACPI0017/CEDT discovery та обмеження endpoint↔memdev relation у sysfs.
- Linux kernel, [Testing CXL](https://docs.kernel.org/next/driver-api/cxl/testing.html) — розподіл ролей cxl_test та KUnit, build instructions і ndctl test integration.
- WSM [QEMU Type 3 model workflow](https://github.com/juv4uk/wsm-desktop/actions/workflows/cxl-qemu-feasibility.yml).
- WSM [Linux guest sysfs workflow](https://github.com/juv4uk/wsm-desktop/actions/workflows/cxl-qemu-guest.yml).

---
**Висновок:** QEMU guest test уже є корисним відтворюваним regression test для CXL enumeration. Наступна інженерна цінність — не створювати region або виконувати RAS команди, а формалізувати безпечне читання topology edges та перевіряти їх на fixtures і QEMU guest.
