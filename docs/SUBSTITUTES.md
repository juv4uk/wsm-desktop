# Субститути WSM: Release assets + GitHub Pages metadata

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **прототип metadata-конвертера; workflow публікації не створено; кеш не опубліковано**
- Ключ підпису: **не створений** — його власник має окремо погодити ownership, custody, backup, rotation і revocation
- Скрипт: [scripts/narinfo_to_release_urls.py](../scripts/narinfo_to_release_urls.py)

## Призначення та межа з Git

Бінарні артефакти збірки (NAR, ISO, bundles) не додаються до source Git branches, включно з окремою orphan-гілкою. Це роздуває об'єктне сховище Git навіть тоді, коли гілка не є main; git push --force не є гарантією негайного звільнення серверного сховища.

Цільова схема для майбутнього substitute endpoint:

| Вміст | Місце |
| --- | --- |
| NAR archives (*.nar) | GitHub Release assets з immutable tag |
| nix-cache-info, *.narinfo, signing-key.pub | статичний GitHub Pages deployment artifact |
| Source code та скрипти | звичайна історія source Git |
| Приватний signing key | owner-controlled secret custody; ніколи не Git, Release або Pages |

Для Pages слід використовувати GitHub Actions upload-pages-artifact та deploy-pages, а не git push у gh-pages. Це публікує лише невеликий metadata site і не створює Git-об'єктів для NAR payloads. Workflow має мати мінімальні Pages permissions, deployment environment github-pages та ручний/захищений approval gate.

## Формат pinned Guix

Розміщення та назви файлів нижче звірено з guix/scripts/publish.scm у Guix commit, зафіксованому в channels.lock.scm:

4e5195be20d9b124df8a8bb69213412236e4668e

Для явного --compression=gzip:

- guix publish --cache=... зберігає NAR за шляхом <cache>/gzip/<store-basename>.nar;
- відповідний .narinfo лежить як <cache>/gzip/<store-basename>.narinfo;
- сам .narinfo містить URL виду nar/gzip/<store-basename> — без .nar суфікса;
- Compression: gzip описує фактичні байти NAR;
- /nix-cache-info та /signing-key.pub — HTTP endpoints сервера, а не файли, які автоматично з'являються в каталозі --cache.

Тому майбутній publisher має явно:
1. використовувати узгоджену compression policy;
2. завантажити NAR cache files як Release assets із точним ім'ям <store-basename>.nar;
3. отримати nix-cache-info і signing-key.pub через відповідні локальні HTTP endpoints та покласти їх у Pages root;
4. скопіювати .narinfo з compression subdirectory у Pages root, переписавши лише URL: на asset URL <store-basename>.nar.

Якщо compression змінюється на zstd, workflow повинен одночасно узгодити параметр --compression=zstd, каталог zstd/, Compression: zstd, вміст NAR asset та URL. Не називати архів .nar.zst, якщо саме такі байти й імена не створені та не перевірені.

## URL converter

scripts/narinfo_to_release_urls.py — лише локальний transform для metadata. Він:

- читає .narinfo з вкладених compression directories;
- вимагає рівно одне поле URL:;
- переписує його на <release-base>/<store-basename>.nar;
- відхиляє записи без NAR basename та порожні cache trees;
- розкладає .narinfo у metadata destination root;
- перевіряє побайтно, що після нормалізації тільки URL value весь решта документ не змінився.

Guix підписує канонічну частину, що включає StorePath, NarHash, NarSize, References і optional Deriver; URL, Compression та FileSize додаються після підпису. Отже, URL rewrite сумісний з моделлю Guix narinfo лише за умови, що всі інші байти залишаються незмінними. Unit-тест цього скрипта не замінює криптографічну перевірку справжнього .narinfo pinned Guix consumer-ом.

## Майбутній publication pipeline (ще не реалізований)

На окремому, owner-approved publishing runner концептуальний порядок такий:

1. За погодженою signing-key policy виконати package build лише з точними довіреними Guix/WSM commits.
2. Запустити guix publish локально з явними --public-key, --private-key, --compression=gzip і --cache.
3. Запросити /{narinfo-hash}.narinfo для кожного потрібного store path, щоб прогріти lazy cache.
4. Скопіювати /nix-cache-info та /signing-key.pub у Pages root; конвертувати .narinfo у Pages root.
5. Завантажити відповідні <store-basename>.nar як Release assets у release/tag з незмінним URL.
6. Перевірити розміри кожного asset, кількість assets, повноту URL → asset mapping, відсутність NAR binaries у Pages artifact та source Git.
7. Задеплоїти лише metadata root через upload-pages-artifact / deploy-pages.
8. На disposable Guix consumer додати публічний ключ до authorized keys і виконати реальний substitute fetch для test package. Перевірити signature, NAR hash, decompression, store path та exit code.

До реалізації цих кроків цей документ описує design, а не готовий сервер. У репозиторії немає publishing workflow, Release asset uploader чи Pages deployment workflow; narinfo_to_release_urls.py сам по собі не створює й не публікує кеш.

## Використання клієнтом (лише після production approval)

Після того, як owner опублікує перевірений endpoint і public key, клієнтська схема буде такою:

    wget https://juv4uk.github.io/wsm-desktop/signing-key.pub -O wsm.pub
    sudo guix archive --authorize < wsm.pub

    guix build wsm-tools \
      --substitute-urls="https://juv4uk.github.io/wsm-desktop https://ci.guix.gnu.org"

Не виконувати це як production інструкцію, доки Pages endpoint, release assets і key fingerprint не опубліковані та не пройшли disposable-consumer acceptance.

## Обов'язкові owner gates

- **Ліцензія #367:** effective license metadata wsm-tools досі не узгоджена. Підпис не надає прав на розповсюдження; жоден WSM package output не публікувати до вирішення issue.
- **Channel Phase B:** WSM channel ще не має owner-controlled signed introduction/authorization/keyring bootstrap. channels.lock.scm із локальним -L . не доводить authenticated WSM channel.
- **Signing-key custody:** власник має визначити, хто контролює приватний ключ, де зберігаються backup, як відбуваються rotation/revocation та хто схвалює кожен publish. Агент не генерує ключі, не додає secrets і не підписує artifacts від імені власника.
- **Publication approval:** вибір URL, GitHub Pages deployment settings, immutable release naming, trigger policy та публічний client trust — окремі рішення власника.

До закриття всіх gates не створювати keys/secrets, не завантажувати Release assets, не вмикати Pages deployment і не запускати publisher.
