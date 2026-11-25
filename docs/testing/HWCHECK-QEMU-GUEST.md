# Запуск WSM hardware checker у гостьовій Linux-системі QEMU

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Статус: **CI experiment**
- Пов'язано: #3 (hardware preflight), #16 (driver/runtime firmware evidence), #61 (generic QEMU guest), #64 (bounded serial/stderr capture), #66
- Runner: scripts/ci_qemu_hwcheck_guest.py
- Workflow: .github/workflows/hwcheck-qemu-guest.yml

## Що саме перевіряється

GitHub-hosted Ubuntu runner готує тимчасовий initramfs із runner kernel, BusyBox та CPython runtime. Усередині QEMU-гостя виконується реальний код python -m wsm_hwcheck з цього repository commit. Гість читає власні /sys і /proc, формує Hardware Evidence Report v1.0.0 та передає стислий звіт через serial. Host runner розпаковує payload і перевіряє його офіційною JSON Schema з репозиторію.

Це не підмінює collector shell-імітатором і не підставляє host /sys чи /proc: колектор запускається у власному Linux guest kernel і бачить тільки його псевдофайлові системи.

## Runtime CPython

Для цього CI experiment використовується незмінний upstream release python-build-standalone tag 20261123:

- CPython 3.11.18, target x86_64-unknown-linux-gnu;
- archive install_only_stripped;
- SHA-256: 75b92c55bc6a5f58fe4d08fc5261c983b2b17930192d62946fe7c9cf6fd66316;
- завантаження відбувається лише у host runner, з перевіркою digest перед розпакуванням.

GNU/Linux build не називається static. Runner перевіряє ELF-об'єкти у pinned runtime через ldd, відмовляється від unresolved libraries та копіює до initramfs лише виявлені зовнішні shared-library dependencies. Host /lib цілком не копіюється. Python runtime не додається до WSM Guix/Nix closure або production image у межах цього experiment.

## Межі ізоляції

- QEMU TCG, 2 GiB guest RAM, 1 vCPU, обмежений wall-clock timeout.
- Гість завантажується з -kernel та initramfs; віртуального диска або CD-ROM немає.
- -nic none; немає host block device, USB/GPU passthrough, shared folders або EFI variable store.
- Python archive завантажується host runner до створення guest; гість не має мережевого інтерфейсу.
- Завантаження CPython обмежено 40 MiB; tar — 50 000 записів і 256 MiB розпакованих файлів; initramfs — 256 MiB; JSON-звіт — 512 KiB до gzip/base64.
- Serial і stderr читаються через спільний bounded QEMU reader (1 MiB serial, 256 KiB stderr); зберігаються лише обмежені хвости. Переповнення capture — hard failure, частковий звіт не приймається.
- JSON Schema перевіряється на host. У гості немає jsonschema, pip чи package manager.

## Acceptance та інтерпретація

Успіх означає, що справжній guest kernel запустив /init, CPython імпортував потрібні стандартні модулі, wsm_hwcheck прочитав guest /sys і /proc, згенерував звіт, а host успішно перевірив schema v1.0.0 та privacy flags.

Перевірка вимагає network_requests_performed=false, network_upload_performed=false і не дозволяє inventory-only run видати functional test зі статусом passed. Стани unknown або відсутність functional tests залишаються невизначеністю, а не доказом несумісності чи позитивної працездатності.

Це QEMU guest runtime validation, а не WSM ISO boot, Guix system build, інсталяція на диск, physical hardware test або глобальна сертифікація сумісності.
