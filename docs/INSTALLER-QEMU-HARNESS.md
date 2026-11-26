# Ручний QEMU harness для WSM installer

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **локальний harness; runtime acceptance запускається вручну**
- Реалізація: `scripts/qemu_boot_smoke.py`
- Ручні guest checks: [testing/QEMU-GUEST-CI.md](testing/QEMU-GUEST-CI.md)

## Що робить harness

Project harness приймає наявний ISO-файл, перевіряє обмеження диска/RAM/CPU/часу, створює новий qcow2 у тимчасовому каталозі й запускає QEMU з TCG та вимкненою мережею. За потреби можна вимагати точний boot marker.

Serial stdout і QEMU stderr читаються паралельно в буфери обмеженого розміру. JSON-звіт містить хвіст виводу, кількість побачених байтів і прапорці обрізання. Marker шукається в усьому serial stream, навіть якщо його байти вже не входять у збережений хвіст. Після timeout процес QEMU завершується, а потоки закриваються.

Блокові пристрої передаються через структуровані QEMU `-blockdev` arguments. Host block devices не підключаються. Немає USB/GPU passthrough, shared folders або EFI variable store.

## Ручний запуск

```sh
python scripts/qemu_boot_smoke.py --help
python scripts/qemu_boot_smoke.py --iso /absolute/path/to/image.iso
```

Для повного набору disposable guest checks:

```sh
make qemu-acceptance-manual
```

Ці перевірки не запускаються автоматично в GitHub Actions. Hosted CI обмежений швидкими unit/policy tests, документацією та структурними channel checks.

## Що означає успіх

Успішний generic guest boot доводить, що конкретне ядро та init-процес запустилися під QEMU TCG. Запуск конкретного ISO доводить лише, що harness зміг стартувати цей ISO та зафіксувати потрібний marker у вибраному сценарії.

Це не доводить:

- що ISO є Guix-generated WSM image;
- що WSM installer виконав встановлення;
- що система завантажується на фізичному ПК;
- що GPU, Wi-Fi, audio, display, storage або firmware фізичного хоста сумісні.

Не використовуйте generic guest marker як hardware compatibility evidence або як заяву про готовність інсталятора.

## Ізоляція

- QEMU працює через TCG; KVM і host CPU passthrough не потрібні.
- Guest networking вимкнено.
- Writable qcow2 та тимчасові файли створюються у приватному тимчасовому каталозі й видаляються після запуску.
- Немає host disks, host block devices, USB/GPU passthrough, shared host folders або EFI variable store.
- Harness не запускає Guix/Nix deployment, firmware updater чи installer APPLY.
