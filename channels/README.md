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

[`wsm.scm`](wsm.scm) — набір, який робить `(wsm packages wsm)` доступним **як
канал**, а не через `-L "$PWD"`:

```sh
guix time-machine -C channels/wsm.scm -- describe      # відмова: не автентифіковано
guix time-machine -C channels/wsm.scm --disable-authentication -- describe
```

Друга команда працює вже сьогодні. Саме тому нею не користуються для релізних
збірок: вона вимикає ту саму перевірку, яку проєкт обіцяє.

Це **не** lock: `wsm` тут іде за гілкою `main`, бо канал ще не має
introduction. Релізні збірки й далі використовують `channels.lock.scm` із
точними commit-ами.

## Набір каналів WSM (не release lock)

`wsm.scm` додає WSM до канонічного `%default-channels` із `(guix channels)`. Офіційний Guix channel не копіюється в окремий record: branch та introduction залишаються авторитетними в самій версії Guix. WSM іде за `main`, але поки не має власного introduction, тому звичайна автентифікація має відмовити:

```sh
guix time-machine -C channels/wsm.scm -- describe -f channels
```

Діагностичне читання:

```sh
guix time-machine -C channels/wsm.scm --disable-authentication -- describe -f channels
```

**Увага:** `--disable-authentication` лише підтверджує, що Guix прочитав набір каналів `guix,wsm`. Це завжди `WSM_CHANNEL_AUTHENTICATION=NOT_TESTED`; ця команда заборонена для release, installer та production. Цей файл не є release lock і не замінює owner-signed Phase B. Для релізів використовуються окремі pinned locks із точними commit-ами.

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
