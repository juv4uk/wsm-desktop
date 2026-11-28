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

## Набір каналів WSM (не lock)

[`wsm.scm`](wsm.scm) — набір для розробки, який об'єднує офіційний GNU Guix
channel на рухомій гілці `master` із репозиторієм WSM на гілці `main`.
Офіційний Guix channel містить canonical introduction; WSM поки не має
власного introduction.

Звичайна команда має відмовити на автентифікації WSM:

```sh
guix time-machine -C channels/wsm.scm -- describe -f channels
```

Діагностичне читання без перевірки автентифікації:

```sh
guix time-machine -C channels/wsm.scm --disable-authentication -- describe -f channels
```

**Не використовуйте** `--disable-authentication` у release, installer або
production workflow. Успішне діагностичне читання не є доказом автентифікації:
звіт повинен залишатися `WSM_CHANNEL_AUTHENTICATION=NOT_TESTED`.

Це **не** release lock. Релізні збірки й далі використовують
`channels.lock.scm` із точними commit-ами. Для переходу WSM на звичайний
authenticated channel спершу потрібні owner-signed introduction commit,
`.guix-authorizations`, public-only `keyring` branch і успішна consumer-side
перевірка `guix git authenticate`. Не вигадуйте fingerprint і не передавайте
секретний ключ у GitHub/CI.

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
