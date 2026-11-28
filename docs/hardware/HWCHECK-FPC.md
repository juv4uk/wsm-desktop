# Native FPC collector — експериментальний пакет WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **native prototype / не є заміною чинного `wsm-hwcheck` до завершення parity та package acceptance**
- Пакет: `wsm-hwcheck-fpc`
- Guix module: `(wsm packages wsm-fpc)`
- Джерело: `tools/fpc/`
- JSON contract: [WSM Hardware Report 1.1.0](REPORT-FORMAT.md) та [schema](../../schemas/hardware-report.schema.json)

## Мета

Нативний Free Pascal executable без CPython у runtime closure. FPC і GNU Make потрібні лише під час збірки пакета; установленим файлом є `/bin/wsm-hwcheck`. Пакет поширюється під ВОЛЬНІСТЮ, як і решта власної роботи WSM.

Це не Lazarus GUI і не LCL-програма. CLI використовує FPC RTL та FCL JSON (`fpjson`); воно не запускає Python як subprocess і не делегує інвентаризацію зовнішнім командам.

## Збірка та запуск

У середовищі з Free Pascal 3.2.2 і FCL units:

```sh
make -f tools/fpc/Makefile build
make -f tools/fpc/Makefile test
./build/fpc/wsm-hwcheck
./build/fpc/wsm-hwcheck --compact
./build/fpc/wsm-hwcheck --output ./hardware-report.json
```

Побудувати Guix package із зафіксованим офіційним Guix lock:

```sh
guix time-machine -C channels.lock.scm -- build -f wsm/packages/wsm-fpc.scm
```

CLI підтримує `--version`, `--help`, `--output PATH`, `--compact`, `--sysfs-root PATH` та `--proc-root PATH`. Без `--output` звіт іде тільки в stdout; файл не створюється неявно.

## Поточний обсяг доказів

| Область | FPC prototype | Принцип |
|---|---|---|
| Архітектура, kernel release, boot mode | Читає procfs/sysfs | Недоступне лишається `unknown` |
| DMI / BIOS / motherboard | Читає доступні DMI-поля | Не читає serial number |
| CPU identity | Читає `/proc/cpuinfo` та microcode revision sysfs | ISA contract — окремий |
| PCI identity та driver binding | Vendor/device/subsystem/revision/class/modalias, symlink driver | Binding не означає функціональність |
| GPU facts | Boot VGA, DRM card nodes, PCIe link | Не є графічним функціональним тестом |
| USB | Parent device identity та driver link | Composite interface topology поки не збирається |
| Storage | Capacity, sector sizes, rotational/removable/read-only, sysfs partitions, transport | Не читає GPT contents/filesystems; не пише на диск |
| DRM displays | Connector, connection state, advertised/active modes | EDID decoding та connector-to-GPU topology не реалізовані |
| Runtime module/firmware diagnostics | Поки `unknown` | Kernel log і `modules.alias` stage не портовані |

Усі записи мають WSM Hardware Report schema `1.1.0`. Пристрій, який знайдено, але не протестовано функціонально, не отримує `passed`. Діагностичні прогалини записуються у `limitations`; не підмінюються припущеннями.

## Приватність та межі

- Лише локальні read-only sysfs/procfs; мережеві запити й upload не виконуються.
- Не читаються серійні номери, MAC-адреси, UUID, hostname, username, IP чи storage WWN.
- Не завантажуються/вивантажуються модулі, не змінюється firmware, не монтуються розділи та не виконується `mkfs`, partitioning чи `guix system init`.
- JSON report створюється у файлі лише за явним `--output`.
- Наявний Python collector лишається reference для порівняння, доки FPC не пройде схему, fixture-based parity для всіх collectors, package build та live/QEMU acceptance. Python-based installer не оголошується заміненим цим пакетом.

## Acceptance, що лишається відкритим

1. Реальна збірка FPC 3.2.2 у CI та Guix із тим самим source.
2. JSON Schema validation із перевіркою `format` для date-time/date/URI.
3. PCI identity parity на тих самих sysfs/procfs коренях.
4. Знеособлені fixture trees для CPU/DMI/PCI/USB/storage/DRM та негативні тести відсутніх/пошкоджених джерел.
5. Closure/package acceptance: FPC тільки build-time, жодних Python/FCL runtime package dependencies.
6. Live/QEMU proof, що executable є в image і поводиться read-only.

До виконання цих gates пакет — окремий native prototype, не default dependency live ISO і не повна заміна `wsm-tools`.