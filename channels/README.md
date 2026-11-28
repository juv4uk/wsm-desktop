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

## Набір каналів WSM (не release lock)

[`wsm.scm`](wsm.scm) додає WSM channel до `%default-channels` GNU Guix.
Тому URL, introduction та інші upstream defaults залишаються авторитетними
в самому Guix, а WSM задається окремо на рухомій гілці `main`.

Звичайна автентифікація має відмовити саме через відсутній WSM introduction:

```sh
guix time-machine -C channels/wsm.scm -- describe -f channels
```

Локальна діагностика може перевірити, що Guix читає обидва записи, але лише
з явним обходом автентифікації:

```sh
guix time-machine -C channels/wsm.scm --disable-authentication -- describe -f channels
```

Цей обхід ніколи не є production/release режимом. Такий прогін доводить лише
читання конфігурації каналів і мусить звітувати
`WSM_CHANNEL_AUTHENTICATION=NOT_TESTED`.

Це **не** lock. Релізні збірки продовжують використовувати
`channels.lock.scm` із точними commit-ами. До додавання WSM у будь-який
release lock власник має локально завершити trust bootstrap: підписаний
introduction commit, `.guix-authorizations`, public-only `keyring` branch
і consumer-side `guix git authenticate` зі звичайною автентифікацією.
Не вигадуйте fingerprint і не передавайте секретний ключ у GitHub/CI.

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
