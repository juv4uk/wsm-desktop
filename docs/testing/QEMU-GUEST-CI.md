# Ручні QEMU runtime-перевірки

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **ручне acceptance; не запускається в hosted CI**
- Швидкий CI: `.github/workflows/ci.yml`
- Ручна команда: `make qemu-acceptance-manual`
- Суміжний контракт: [INSTALLER-QEMU-HARNESS.md](../INSTALLER-QEMU-HARNESS.md)

## Межа швидкого CI

Hosted CI навмисно виконує лише Python unit/policy tests, перевірку документації та структурні перевірки двох channel locks. Він не встановлює QEMU, Guix чи пакети ОС, не збирає ISO й не запускає гостьові системи. Звичайний push або PR має завершуватися швидко й не чекати на runtime acceptance.

## Ручне QEMU acceptance

Запускати окремо на Linux host із QEMU, BusyBox, cpio, modprobe та Python-залежністю `jsonschema[format]==4.26.0`:

```sh
make qemu-acceptance-manual
```

Ціль послідовно запускає:

1. `scripts/ci_qemu_guest_smoke.sh` — generic Linux guest boot під QEMU TCG без диска й мережі; очікуваний маркер `WSM_QEMU_GUEST_INIT_OK`.
2. `scripts/ci_qemu_hwcheck_guest.py` — реальний `wsm-hwcheck` усередині disposable guest; runtime CPython завантажується за зафіксованим SHA-256, звіт передається через serial і перевіряється на host.
3. `scripts/ci_cxl_qemu_guest.py --timeout 90` — read-only CXL Type 3 enumeration у гостьовому ядрі; host-модулі не завантажуються й host sysfs не змінюється.

Команди можна запускати окремо для локалізації проблеми. Відсутні інструменти, модулі або права мають завершуватися явною помилкою, а не пропуском із PASS.

## Ручна перевірка конкретного ISO

Для перевірки вже зібраного ISO використовуйте project harness:

```sh
python scripts/qemu_boot_smoke.py --help
python scripts/qemu_boot_smoke.py --iso /absolute/path/to/image.iso
```

Harness створює одноразовий qcow2 у тимчасовому каталозі, працює через TCG без мережі й не підключає host block devices, USB/GPU passthrough, shared folders або EFI variable store. Це перевіряє лише запуск вибраного ISO в межах заданого сценарію; результат не є доказом фізичної сумісності.

## Інші повільні перевірки

Guix evaluation також запускається лише за явною командою:

```sh
make check-guix-eval
```

Локальні unit-тести аргументів і harness залишаються у швидкому наборі тестів; вони не запускають QEMU guest. Повне runtime acceptance навмисно відокремлене від `make check` і hosted CI.
