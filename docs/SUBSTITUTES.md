# Статичний кеш substitutes WSM — технічний прототип

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **конвертер метаданих має тести; package build і публікація не запускалися**
- Ключ підпису: **не створений** — його може створити лише власник після окремого рішення
- Рішення про substitute endpoint, ключ і хостинг: **відкрите**, див. GUIX-CHANNEL.md
- Скрипт: scripts/narinfo_to_release_urls.py

## Призначення та межі

Це прототип для перетворення підписаних Guix narinfo у статичні метадані з URL архіву, розміщеного як release asset. Він не збирає пакети, не створює підпис, не генерує nix-cache-info чи signing-key.pub і нічого не публікує.

Схема лише запропонована; вона не є затвердженим власником рішенням про substitute-сервер.

## Формат pinned Guix

У pinned Guix з channels.lock.scm guix publish використовує gzip, якщо явно не задано іншу компресію. Для відтворюваності майбутня owner-operated команда має задавати --compression=gzip явно.

Локальний cache layout за цієї опції:

| Тип | Шлях у каталозі --cache |
| --- | --- |
| narinfo | gzip/<store-basename>.narinfo |
| NAR archive | gzip/<store-basename>.nar |

У narinfo поле URL для цього режиму має вигляд nar/gzip/<store-basename>; суфікса .nar у URL немає. Конвертер за замовчуванням залишає лише basename і підставляє base URL release assets. Прапорець --keep-path зберігає весь відносний шлях, включно з nar/gzip/.

Pinned Guix формує підписаний payload від StorePath до Signature (включно з NarHash, NarSize, References і, якщо є, Deriver). URL, Compression і FileSize додаються після Signature. Конвертер вимагає рівно один Signature та один URL, вимагає URL після Signature і змінює лише значення URL. Це структурна гарантія незмінності підписаного тексту, **не криптографічна перевірка підпису**.

## Майбутній owner-operated процес — не запускався

Публікація можлива лише після окремого рішення власника про endpoint, signing-key custody, Phase B та завершення license review #367. Приклад нижче описує очікувану структуру, але це не команда для агента і не доказ, що процес уже працює.

    guix publish --compression=gzip --cache=/var/cache/publish --port=3000

    for store_path in $(guix build wsm-tools --no-substitutes); do
      basename=$(basename "$store_path")
      hash=$(printf '%s' "$basename" | cut -d- -f1)
      curl -fsS "http://localhost:3000/$hash.narinfo" >/dev/null
    done

Guix publish формує cache entries ліниво — запит narinfo прогріває відповідний запис. Cache archives лежать у /var/cache/publish/gzip/<store-basename>.nar; narinfo — у /var/cache/publish/gzip/<store-basename>.narinfo.

nix-cache-info та signing-key.pub є HTTP endpoints сервера, а не файлами всередині --cache. Якщо власник затвердить статичний endpoint, їх треба окремо отримати з локального сервера й розмістити в корені metadata site:

    mkdir -p ./site
    curl -fsS http://localhost:3000/nix-cache-info -o ./site/nix-cache-info
    curl -fsS http://localhost:3000/signing-key.pub -o ./site/signing-key.pub

Після цього narinfo можна конвертувати, залишаючи URL basename для release asset. Файл NAR з локального gzip cache має суфікс .nar; release asset має бути опублікований під basename, який вказано в narinfo URL.

    python3 scripts/narinfo_to_release_urls.py \
      --source /var/cache/publish/gzip \
      --destination ./site \
      --base-url "https://github.com/juv4uk/wsm-desktop/releases/download/substitutes"

Не використовувати --keep-path, якщо release assets лежать у корені release. Жоден із цих кроків не виконано в цьому проєкті.

## Що тут не вирішено

- Ключ підпису не створений; агент не генерує і не зберігає приватні ключі від імені власника.
- Substitute endpoint та схема хостингу не затверджені власником.
- wsm-tools closure ще не зібрана; її розмір не виміряний.
- Package/license metadata issue #367 не вирішений; публічне розповсюдження substitutes заборонено до owner/legal decision.
- WSM channel Phase B не виконано: немає owner-signed introduction, .guix-authorizations і public keyring. URL rewrite не обходить channel authentication.
- Не запускали guix publish, cache warming, upload або consumer authorization.
- Тести перевіряють лише форматування й незмінність signed payload bytes; вони не доводять валідність підпису чи роботу substitute endpoint.
