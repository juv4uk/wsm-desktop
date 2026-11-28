# Субститути WSM — ручна публікація увімкнена, кеш ще не опублікований

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Workflow: **enabled**, запуск лише через `workflow_dispatch`.
- Перша ціль: WSM-owned пакет `wsm-tools`.
- Guix input: exact revision із `channels.lock.scm`.
- NAR export / GitHub Release: **ще не виконано**.
- Narinfo / GitHub Pages: **ще не опубліковано**.
- Підпис: приватний ключ береться тільки із секрету Actions `GUIX_SIGNING_KEY`.
- Cuirass: окремий build coordinator; його інстанс ще не запускався.

## Що запускає workflow

Поточний `.github/workflows/substitutes.yml` виконує ручну збірку одного локального пакета WSM. Команда використовує зафіксований офіційний Guix lock і явно завантажує модуль із checkout цього workflow:

```sh
guix time-machine -C channels.lock.scm -- build --no-substitutes \
  -L . -e '(@ (wsm packages wsm) wsm-tools)'
```

Це важливо: `wsm-tools` не є пакетом стандартного upstream Guix, тому голий `guix build wsm-tools` не може його знайти. WSM source береться з exact checkout commit GitHub Actions; це не означає, що WSM channel уже пройшов `guix git authenticate`.

Після збірки workflow запускає `guix publish`, читає `URL:` із кожного narinfo та робить GET самого NAR, щоб Guix створив стиснений архів у `/var/cache/publish/nar`. Перед завантаженням workflow перевіряє, що `.nar.zst` справді з'явився:
- NAR-файли завантажуються як assets GitHub Release `substitutes`;
- narinfo та `nix-cache-info` публікуються через GitHub Pages;
- `signing-key.pub` надається разом із metadata.

`.github/workflows/package-archives.yml` — legacy workflow; він не є поточним шляхом substitute cache.

## Підписний ключ і довіра

Для підписаного Guix substitute cache потрібен постійний owner-controlled key. Його не можна вигадувати, комітити до репозиторію або генерувати щоразу заново: клієнти мають довіряти тому самому публічному ключу.

Створення на власній машині:

```sh
sudo guix archive --generate-key
gh secret set GUIX_SIGNING_KEY --repo juv4uk/wsm-desktop \
  < /etc/guix/signing-key.sec
```

Workflow відмовляється публікувати непідписаний кеш, якщо секрет недоступний. Стан GitHub Actions secret не можна підтвердити через GitHub repository connector; його має підтвердити ручний workflow run. Приватний ключ не повинен з'являтися в Git, release assets або workflow logs.

Це дві різні довіри:
1. Підпис Guix narinfo підтверджує, що substitute cache підписано довіреним cache key.
2. `guix git authenticate` перевіряє історію самого WSM channel. У каналі ще немає owner-signed introduction, `.guix-authorizations` та keyring branch. Ручна збірка з pinned source checkout не заявляє, що WSM channel authenticated.

## Ліцензія та межі пакета

Правовласник 2026-11-28 прямо доручив публікувати власні WSM package outputs через WSM-owned substitute cache. Метадані `wsm-tools` та WSM live helper packages мають посилатися на фактичну ВОЛЬНІСТЬ (`file://LICENSE`), а не помилково представляти WSM code як GPL-3+. Це вузький дозвіл на WSM-owned outputs; він не є висновком про OSI або GNU FSDG та не підтверджує прийнятність цієї ліцензії для upstream GNU Guix distribution.

Цей дозвіл не поширюється на NVIDIA GP107 firmware, proprietary NVIDIA 580.x або інші сторонні binary components. Для них потрібні окремі ліцензійні права та package/runtime evidence. Відкритий GP107/Nouveau/NVK і proprietary NVIDIA залишаються окремими, взаємовиключними Compatibility дослідженнями; їх не можна непомітно додавати у Free closure.

## Статус

PR #771 увімкнув ручний substitute workflow. PR #774 виправляє local package lookup та фактичне прогрівання NAR cache; доки він не пройшов exact-head CI, ручний workflow run і release read-back, NAR не вважається опублікованим.

Публікація не запускається автоматично на кожен push до `main`. Жодного substitute cache ще не опубліковано.
