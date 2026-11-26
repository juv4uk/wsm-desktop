# Псевдографічний вибір цілі та preview

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальний APPLY вимкнено**
- Код: [`wsm_install/tui.py`](../wsm_install/tui.py)
- Тести: `tests/test_tui.py`

## Три frontend-и — одна межа

| Вхід | Кому | Дозволено зараз |
| --- | --- | --- |
| `--guided` | послідовна лінія, скрипт, простий термінал | вибір диска та preview |
| `--tui` | екран із клавіатурною навігацією без desktop | вибір диска та preview |
| Calamares | машина з Qt | jobmodule preview, що явно повідомляє: систему не встановлено |

Усі входи використовують спільні `partition.py`, `install_steps.py` та
preview-only `executor.py`. Жоден із них не запускає `sgdisk`, `mkfs`,
`mount` або `guix system init`.

## Як виглядає

```text
┌────────────────────────────────────────────────────────────┐
│ WSM install                                                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Choose a disk to preview:                                  │
│                                                            │
│ > 1. /dev/nvme0n1       256 GiB                            │
│   2. /dev/sda           120 GiB  removable                 │
│                                                            │
│ ↑/↓ or j/k to move, Enter to choose, q to quit.            │
└────────────────────────────────────────────────────────────┘
```

Далі користувач обирає UEFI або BIOS, вводить шлях диска для підтвердження,
який саме target описувати, і бачить preview. Фінальний екран повідомляє:
APPLY вимкнено, жодна дискова команда не запускалася, система не встановлена.

## Чому не curses

`curses` є у стандартній бібліотеці, але тягне обробку можливостей термінала й
глобальний стан екрана, який важко тестувати та який ламається на послідовних
консолях.

Тут екран — список рядків плюс читач клавіш. Обидва ін'єктовані, тому тести
перевіряють рамки, навігацію, backspace, firmware selection, відмову при
неправильному шляху та випадок помилки preview без реального термінала.

## Точна межа підтвердження

Введення `/dev/nvme0n1` визначає тільки target preview. Воно не є згодою на
форматування, не доводить фізичну ідентичність пристрою й не замінює
major/minor, capacity та partition-topology probe. Enter не запускає
встановлення; окремого install callback у TUI немає.

Якщо `stdin` або `stdout` не є терміналом, `--tui` переходить на guided
консольний preview і пояснює це в stderr.

## Умови для майбутнього APPLY

Див. [EXECUTOR.md](EXECUTOR.md): immutable target-bound plan, independently
observed device identity, digest-bound consent, verified Guix tool closure,
real postconditions, recovery semantics і destructive acceptance на
disposable QEMU.
