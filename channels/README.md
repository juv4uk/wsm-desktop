# Канали WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Free

`../channels.lock.scm` — окремий release lock тільки з офіційним каналом GNU
Guix. Він фіксує точний commit та introduction. Структурна перевірка виконується
так:

```sh
python3 scripts/check_channels.py --policy free --lock channels.lock.scm
guix time-machine -C channels.lock.scm -- describe -f channels
```

Перша команда перевіряє Scheme-структуру й allowlist. Друга — незалежно
виконує channel authentication у Guix. PASS лише структурної перевірки не
доводить криптографічну автентифікацію.

## Compatibility

`compatibility.lock.scm` — pin Guix + Nonguix для окремого Compatibility
образу. Не змішуйте його з Free lock:

```sh
python3 scripts/check_channels.py --policy compatibility --lock channels/compatibility.lock.scm
guix time-machine -C channels/compatibility.lock.scm -- describe -f channels
guix time-machine -C channels/compatibility.lock.scm -- system build systems/live-compat.scm --dry-run
```

Структурний checker підтверджує лише точні назви каналів, repository URLs,
commit pins та canonical introduction metadata. Він не перевіряє підпис
конкретного commit. Це робить Guix channel authentication; live-compat
evaluation окремо доводить, що закріплена композиція може бути обчислена.

## Рухомі визначення

- `free.scm` — рухома база Free для розробки, не release lock.
- `compatibility.scm` — явне додавання Nonguix, не release lock.
- `../channels.lock.scm` і `compatibility.lock.scm` — окремі pinned inputs
  для двох продуктів. Жоден із них не змінює глобальну конфігурацію Guix хоста.
