# Псевдографічний інсталятор

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; APPLY вимкнено**
- Код: [`wsm_install/tui.py`](../wsm_install/tui.py)
- Тести: `tests/test_tui.py`

## Призначення

`--tui` — нуль-залежний клавіатурний інтерфейс для live-середовища без
робочого столу. Він дозволяє вибрати цільовий диск, firmware mode і сформувати
read-only план. Він **не** форматує, не монтує, не запускає Guix init і не
встановлює систему.

## Послідовність

1. Вибір диска зі списку sysfs.
2. Вибір UEFI/BIOS.
3. Повторне введення шляху — підтвердження лише preview, не згода на запис.
4. Показ read-only плану з явним статусом `APPLY disabled; system NOT installed`.

У TUI немає install callback, другого «Enter to install» або команди запису.
CLI `--execute`, guided flow та Calamares мають таку саму fail-closed межу.

## Чому без сторонньої TUI-залежності

Для мінімального live образу залишено стандартний Python, ANSI та POSIX termios.
Textual/prompt_toolkit можуть бути окремими optional packages для розширеного UI,
але не повинні збільшувати closure recovery/live image без потреби.

## Обмеження

- Фіксована ширина 62 колонок; на вузьких терміналах можливе обрізання.
- Реальний запуск у фізичній консолі не підтверджений.
- Package closure і tty support треба підтвердити окремим Guix build та QEMU acceptance.
