# Канали WSM

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

## Вільний релізний lock

`../channels.lock.scm` — автентифікований snapshot **тільки офіційного каналу Guix** для WSM Hardware Preview RC1. Він містить точний commit `4e5195be20d9b124df8a8bb69213412236e4668e` і channel introduction з OpenPGP fingerprint. Немає Nonguix, nonfree firmware, додаткових substitute serverів чи ключів.

Lock створено з ізольованого профілю, де `guix pull` виконувався **без** `--disable-authentication`; результат `guix describe -f channels` містить `make-channel-introduction`. Докази й командний лог — у [#39](https://github.com/juv4uk/wsm-desktop/issues/39).

Використання з кореня репозиторію:

```sh
guix time-machine -C channels.lock.scm -- describe -f channels
guix time-machine -C channels.lock.scm -- system build systems/minimal.scm
guix time-machine -C channels.lock.scm -- system vm --no-graphic systems/minimal.scm
```

`guix time-machine -C channels.lock.scm -- describe -f channels` друкує розв'язані revisions; саме цей вивід варто додавати до звіту про відтворення. Команда може попередити «channel is not trusted», якщо цей local channels-файл не внесено до `~/.config/guix/trusted-channels.scm`; це не failing signature. У перевірці RC1 `time_machine_exit=0` без `--disable-authentication`. Не оновлюйте lock автоматично разом із звичайними pull-ами: це pinned fact, а не рухома гілка.

## Поточні файли

- `free.scm` — `%default-channels`, рухома база для розробки; не є release lock.
- `compatibility.scm` — додає Nonguix як **явну опцію**; не використовується у free-профілі RC1.
- `../channels.lock.scm` — автентифікований release lock RC1.

Жоден із цих файлів не змінює глобальну конфігурацію Guix хоста. Для ізольованих експериментів у цьому проєкті використовується окремий Guix daemon з приватними `/gnu/store` і `/var/guix`.
