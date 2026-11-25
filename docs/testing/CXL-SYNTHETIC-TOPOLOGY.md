# Синтетичне тестування CXL: QEMU, cxl_test і sysfs-фікстури

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Дата перевірки джерел: 25 листопада 2026 року
- Статус: feasibility note; експеримент на реальному QEMU guest ще не виконано
- Пов'язано: #94 (CXL synthetic topology), #18 (device topology), #79 (ізольований QEMU guest runner)
- Межа: лише тестова інфраструктура; схема, колектор та політика інсталятора не змінюються

## Висновок

Для WSM потрібні три різні рівні тестів. Їх не слід змішувати або подавати як взаємозамінні:

1. **Synthetic sysfs fixtures** — основа швидких і детермінованих тестів парсера та семантичного валідатора. Вони перевіряють правильність читання вже сформованих об'єктів і зв'язків, але не запускають kernel driver.
2. **Linux `cxl_test`** — найкращий upstream-шлях для перевірки поведінки CXL driver stack на живій емуляційній топології та реальному sysfs ABI. Він потребує спеціально зібраних kernel modules і окремого тестового kernel.
3. **QEMU CXL Type 3** — end-to-end перевірка PCI/ACPI enumeration у справжньому guest kernel. Вона корисна для однієї-двох контрольних топологій, але сама собою не перевіряє повний протокол когерентності, фізичне обладнання або працездатність регіону пам'яті.

**Рекомендація:** спочатку побудувати synthetic fixtures для майбутнього #18; паралельно перевірити наявність CXL-конфігурації та модулів у середовищі #79; окремий QEMU Type 3 smoke запускати лише після проходження цього gate. Для широкого тестування драйверів використовувати окремий `cxl_test` lane, а не роздувати базовий `make check` чи обов'язковий hardware preflight.

## Перевірені upstream-можливості

### QEMU CXL

Стабільний upstream-реліз QEMU на дату перевірки — **11.1.3 від 28 жовтня 2026 року**; 11.2.0-rc1 від 18 листопада є кандидатом у випуск, а не базовою версією для відтворюваного тесту.

Офіційна документація описує CXL 2.0+ emulation, host bridges, root ports, switches, Type 3 volatile/persistent memory, HDM decoders, DOE, AER та IDE. Для мінімального WSM smoke достатньо одного volatile Type 3 пристрою без switch і без створення memory region.

Приклад device topology з офіційної документації QEMU:

```sh
qemu-system-x86_64 \
  -M q35,cxl=on \
  -m 4G,maxmem=8G,slots=8 \
  -smp 4 \
  -object memory-backend-ram,id=vmem0,share=on,size=256M \
  -device pxb-cxl,bus_nr=12,bus=pcie.0,id=cxl.1 \
  -device cxl-rp,port=0,bus=cxl.1,id=root_port13,chassis=0,slot=2 \
  -device cxl-type3,bus=root_port13,volatile-memdev=vmem0,id=cxl-vmem0 \
  -M cxl-fmw.0.targets.0=cxl.1,cxl-fmw.0.size=4G
```

Це фрагмент конфігурації CXL-пристроїв, а не повна команда запуску WSM guest: kernel, initramfs, serial console, timeout та bounded output мають надходити з окремого runner. У CI потрібно додати `-nodefaults`, `-no-user-config`, `-nic none` і не передавати гостьовій системі жодних host block devices, USB/GPU passthrough або shared folders.

Важливі межі QEMU-моделі:

- Документація прямо обмежує модель одним host і статичною topology; fabric management не моделюється.
- QEMU не емулює CXL cache-coherency protocol. Усі твердження про когерентність, реальний bandwidth/latency, RAS recovery чи фізичну сумісність поза цим тестом.
- QTG 0 — єдиний QTG, який зараз підтримується моделлю QEMU.
- Для першого smoke перевіряти лише discovery та read-only topology. Не запускати `cxl create-region`, не програмувати decoders і не додавати CXL memory до системного RAM: це вже інший тест із конфігураційними записами та більшим ризиком.

QEMU Type 3 з volatile memory доступний і в документації гілки 8.2; тому не слід автоматично вважати, що поточний Ubuntu QEMU 8.2.x не має CXL. Але WSM має перевіряти фактичну збірку: наявність device models і успішне розбирання `q35,cxl=on` — обов'язковий preflight, а не припущення за номером пакета. Для контрольного baseline рекомендовано зафіксувати stable 11.1.3 та точний build/package origin.

### Linux `cxl_test`, ndctl і KUnit

Поточна документація Linux розрізняє два шляхи:

- `cxl_test` із `tools/testing/cxl/` емулює host bridges, switches, memory devices та mailboxes. Він призначений для тестів, що залежать від живої topology: port/endpoint enumeration, region assembly, decoder commit і sysfs ABI.
- KUnit перевіряє ізольовану логіку без CXL topology: encoding/decoding, interleave/address translation, firmware/device data parsing і mailbox logic через stub transport. KUnit не замінює `cxl_test` для topology tests.

Офіційна процедура `cxl_test`:

```sh
# У корені kernel source tree, що відповідає тестовому kernel:
make M=tools/testing/cxl

# Після встановлення модулів до відповідного тестового kernel:
meson test -C build --suite cxl
```

Модулі потрібно зібрати для того самого kernel, у якому вони завантажуватимуться. Для CI це означає окремий test kernel, узгоджені kernel source/config та module ABI; не можна збирати модулі для одного ядра й завантажувати їх у випадкове ядро GitHub runner.

Документація ndctl містить типовий CXL test config fragment. Основні параметри:

- `CONFIG_CXL_BUS=m`
- `CONFIG_CXL_PCI=m`
- `CONFIG_CXL_ACPI=m`
- `CONFIG_LIBNVDIMM=m`
- `CONFIG_CXL_MEM=m`
- `CONFIG_CXL_PORT=m`
- `CONFIG_CXL_REGION=y`
- для повної ndctl CXL suite додатково: `CONFIG_CXL_REGION_INVALIDATION_TEST=y`, `CONFIG_CXL_FEATURES=y`, `CONFIG_DAX=m`, `CONFIG_DEV_DAX=m`, `CONFIG_DEV_DAX_CXL=m`, `CONFIG_MEMORY_HOTPLUG=y`, `CONFIG_MEMORY_HOTREMOVE=y` та залежності конкретних тестів.

`CONFIG_CXL_PMEM` потрібен для persistent-memory test coverage, але не є умовою лише для первинного volatile Type 3 discovery. Фактичний набір залежить від тестового сценарію; цей список не слід механічно переносити до WSM production kernel.

### Готовий upstream CI для CXL tests

Проєкт [pmem/ndctl-test-runner](https://github.com/pmem/ndctl-test-runner) надає GitHub Actions harness, який:

1. перевіряє окремо задані kernel і ndctl repository/branch;
2. збирає kernel з CXL test config;
3. запускає kernel у QEMU через run_qemu infrastructure;
4. виконує вибрану `cxl` suite та публікує per-test summary/logs.

README описує приклад із CXL maintainer tree `cxl/cxl.git`, branch `next`, ndctl branch `pending`, suite `cxl` і timeout 35 хвилин. На дату огляду репозиторій `ndctl-test-runner` мав commit `7d5619a59f9fe27be38a8c8d643124c00968dab2`.

Це корисний upstream-maintained **reference harness**, але не нова WSM runtime dependency. Якщо його використовувати в окремому WSM research workflow, потрібно зафіксувати commit самого harness, kernel і ndctl; перевірити workflow та всі third-party actions; не передавати secrets; обмежити permissions та зберігати точні revision IDs. Не підключати рухомі `main`/`next`/`pending` як release evidence.

## Що реально видно в Linux CXL sysfs

Kernel driver розділяє логічну topology та memory-device object:

| Sysfs object / link | Що доводить | Обмеження для WSM |
|---|---|---|
| `root0`, `portX` з `devtype=cxl_port` | Kernel створив logical CXL root/port object | Сам факт object не доводить реальну передачу memory traffic |
| `portX/dportY` | Downstream port, який може бути target для decode | Зберігати лише relationship, підтверджений symlink |
| `portX/uport` | Upstream device, що опублікував port capability | Не підміняти це фізичною схемою board |
| `portX/parent_dport`, `endpointX/parent_dport` | Який downstream port батьківського port веде до дочірнього port/endpoint | Це явний kernel edge, його можна тестувати у synthetic graph |
| `endpointX/decoderX.Y` | Endpoint decoder та його властивості | Decoder state не дорівнює memory reliability |
| `root0/decoderX.Y`, `portX/decoderX.Y` | Root/switch decoder object | Частина decoder attributes є writable; preflight читає лише затверджений RO allowlist |
| `memX` | Окремий CXL memory-device object від `cxl_pci` | Kernel sysfs **не містить endpoint↔memdev relationship**; не з'єднувати їх за іменем або порядком |

Для первинної read-only перевірки достатньо перерахувати `/sys/bus/cxl/devices`, прочитати `devtype` та дозволені symlink `uport`, `parent_dport`, `dportY`; зафіксувати наявні decoder object names і типи. Не читати `memX/serial`, firmware unique identifiers або raw poison data.

Не читати/не записувати sensitive чи state-changing surfaces: `security/sanitize`, `trigger_poison_list`, scrub/repair controls, decoder `target*`/commit/region configuration та будь-які firmware update controls. `regionX` не є вимогою для enumeration smoke: region може бути відсутній, якщо гостьова система його не створювала.

## Перевірка середовища перед QEMU експериментом

Успішний #79 використовував гостьове ядро з лінійки Azure runner kernel; попередній exact run зафіксував `7.0.0-1017-azure`. Це **не є доказом**, що потрібні CXL options або modules наявні. Runner images рухаються: публікація Ubuntu 24.04 image від 22 листопада 2026 року вже називає `7.0.0-1020-azure`. Тому у кожному run потрібно зберігати exact output, а не робити висновок із назви `ubuntu-24.04`.

Перший read-only probe має виконати:

```sh
set -eu
uname -r
qemu-system-x86_64 --version
qemu-system-x86_64 -device help | grep -E 'pxb-cxl|cxl-rp|cxl-type3|cxl-upstream|cxl-downstream'
KCFG="/boot/config-$(uname -r)"
if [ -r "$KCFG" ]; then
  grep -E '^CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM)=' "$KCFG" || true
elif [ -r /proc/config.gz ]; then
  zcat /proc/config.gz | grep -E '^CONFIG_CXL_(BUS|PCI|ACPI|MEM|PORT|REGION|PMEM)=' || true
else
  echo "kernel config: unknown"
fi
for module in cxl_core cxl_pci cxl_acpi cxl_mem cxl_port; do
  modinfo "$module" 2>&1 | sed -n '1,4p' || true
done
```

Інтерпретація:

- Відсутність `/boot/config-*` та `/proc/config.gz` означає **unknown**, а не відсутність підтримки.
- `CONFIG_*=m` без доступного точного `.ko` у guest initramfs недостатньо: модуль треба передати з тієї самої kernel build або зібрати разом із test kernel.
- Наявність `modinfo` на host не доводить, що guest initramfs реально завантажив модулі. Потрібні окремі guest-side докази `modprobe/insmod`, driver binding та створених sysfs objects.
- Якщо kernel config або QEMU device models не доступні, сценарій зупиняється як `environment unavailable`; це не CXL incompatibility verdict.

## Порівняння та рекомендований порядок

| Метод | Перевіряє | Не перевіряє | Місце у WSM |
|---|---|---|---|
| Synthetic sysfs fixtures | path resolution, symlink graph, devtype parsing, unknown/dangling edge, privacy filters | Реальний kernel, driver binding, PCI/ACPI discovery | Перший крок для #18; звичайний швидкий CI |
| `cxl_test` + ndctl | Живий CXL driver stack, topology objects, sysfs ABI, region/decoder behavior у тестовому kernel | Фізичний пристрій, firmware implementation, electrical reliability | Окремий повільний/нічний kernel-test lane |
| QEMU Type 3 | Guest PCI/ACPI discovery, CXL driver enumeration, реальні sysfs links у guest kernel | Повна coherency/fabric model, реальні latency/RAS/firmware, фізична сумісність | Один optional end-to-end smoke після kernel/module gate |
| KUnit | Ізольовану kernel logic і parser/helper behavior | Живу topology та PCI device discovery | Upstream driver logic; не заміняє #18 fixtures або `cxl_test` |

Рекомендована послідовність:

1. Для #18 підготувати fixture набір: один прямий root→host bridge→root port→endpoint; switch з двома downstream ports; два Type 3 devices; відсутній endpoint↔memdev edge; dangling symlink; відсутній decoder; partial/inaccessible sysfs; synthetic serial, який має бути відфільтрований.
2. Перевірити QEMU device models і точні `CONFIG_CXL_*`/module inputs у runner. Зберегти `uname -r`, QEMU version, kernel config, `modinfo`, module hashes та exact CI image release.
3. Якщо gate пройдено — зробити окремий disposable no-disk/no-network QEMU guest із одним volatile Type 3 device. Підтвердити лише PCI/ACPI enumeration і RO sysfs edges; не створювати region.
4. Для глибшої топології та поведінки drivers запустити `cxl_test`/ndctl на окремому kernel через dedicated QEMU test lane. Залишити destructive suite вимкненою.
5. Лише після цього розглядати optional CXL provider у звіті #18. Не додавати CXL як обов'язкову вимогу WSM preflight.

## Acceptance для першого QEMU Type 3 smoke

- Exact commit kernel, exact QEMU version/build і runner image записані в артефакті run.
- `q35,cxl=on` та `cxl-type3` успішно створено; guest kernel має потрібні CXL options/modules.
- У guest існує `/sys/bus/cxl/devices`; знайдено щонайменше один очікуваний CXL port/endpoint і один memdev object, якщо драйвер їх експонує.
- Усі relationship edges виводяться лише з перевірених symlink або decoder ABI; endpoint↔memdev лишається `unknown`.
- Увесь probe read-only: немає `cxl create-region`, decoder writes, poison retrieval, scrub, sanitize, firmware actions або memory hotplug.
- Не передаються serial numbers, HPA/DPA координати чи raw poison addresses.
- Немає disk, NIC, host passthrough чи network у тестовому guest; output bounded і зберігає лише потрібні summary/evidence.
- Висновок називається **synthetic QEMU topology enumeration**, не hardware compatibility certification.

## Джерела

1. [QEMU CXL model, limitations and device examples](https://www.qemu.org/docs/master/system/devices/cxl.html)
2. [QEMU official releases](https://www.qemu.org/download/)
3. [Linux: Testing CXL (`cxl_test` and KUnit)](https://docs.kernel.org/next/driver-api/cxl/testing.html)
4. [Linux: CXL driver operation and topology objects](https://docs.kernel.org/driver-api/cxl/linux/cxl-driver.html)
5. [Linux: CXL sysfs ABI](https://docs.kernel.org/admin-guide/abi-testing.html)
6. [ndctl build and CXL test configuration](https://github.com/pmem/ndctl/blob/main/README.md)
7. [ndctl-test-runner: QEMU-based CXL test harness](https://github.com/pmem/ndctl-test-runner/tree/7d5619a59f9fe27be38a8c8d643124c00968dab2)
8. [GitHub Actions Ubuntu 24.04 runner image release 20261122.23](https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20261122.23)
9. [QEMU RFC: initialize Type 3 regions at guest boot](https://lore-kernel.gnuweeb.org/qemu-devel/0b67947b-e4ee-4e47-b61f-c6ae06501298%40gmail.com/T/) — RFC only, not baseline behavior.

## Реалізація CXL guest regression runner

Для повторюваного end-to-end smoke у гілці дослідження додано окремий runner:

- `scripts/ci_probe_qemu_cxl.py` — host-side snapshot kernel config/module artifacts і QEMU qdev topology; не завантажує host modules.
- `scripts/ci_qemu_cxl_guest.py` — копіює лише dependency closure модулів, яку повернув `modprobe --show-depends` для exact `uname -r`, у тимчасовий initramfs; запускає те саме ядро в QEMU TCG із volatile Type 3 device.
- `tests/test_qemu_cxl_probe.py` та `tests/test_qemu_cxl_guest.py` — unit/safety tests; `make check-cxl-guest` запускає ці тести окремо.
- `.github/workflows/qemu-cxl-feasibility.yml` — окрема workflow lane для qdev та guest-stage; не додається до обов'язкового hardware preflight.

У guest CXL modules завантажуються лише в його disposable kernel. `/proc` і `/sys` монтуються read-only. Runner не створює disk, NIC, CXL region чи namespace; не записує decoder configuration і не запускає poison/scrub/ECS/sanitize/repair/erase/firmware actions. Host dependency resolver використовує лише `modprobe --show-depends`; host modules не завантажуються. Serial/stderr обмежені спільним QEMU reader.

На failure path дозволені лише короткі stage/status codes та агреговані counts. Raw `dmesg`, повний sysfs listing, BDF, serial numbers, HPA/DPA coordinates і poison data не виводяться. QEMU запускається з `-no-user-config`, `-nodefaults`, `-nic none` та без дисків/host passthrough.

Позитивний acceptance вимагає не лише QEMU qdev, а фактичного guest-side CXL module load і хоча б одного `mem*` object у `/sys/bus/cxl/devices`; окремо перевіряються доступні `uport`/`dport` symlink-и. Відсутність endpoint↔memdev relationship лишається `unknown`, якщо kernel не експонує прямий edge. Успіх означає лише synthetic QEMU Type 3 enumeration у точному runner kernel/QEMU build.

Поточний QEMU пакунок GitHub runner — 8.2.2, а не upstream stable 11.1.3. Тому для кожного запуску потрібно записувати exact runner image, `uname -r`, QEMU version, module dependency set і workflow head SHA; не переносити цей evidence на іншу комбінацію kernel/QEMU без повторного прогону.
