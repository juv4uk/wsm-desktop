# Субститути WSM — технічний прототип, публікацію вимкнено

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Стан: **NOT_AUTHORIZED / NOT_PUBLISHED**
- Workflow публікації: **вимкнений fail-closed guard**
- Package/NAR export: **вимкнений до licensing decision #367**
- Підписний ключ: **не створений і не збережений у CI**
- Cuirass: **окремий build coordinator; не є автоматичним substitute server**

## Що є в репозиторії

`scripts/narinfo_to_release_urls.py` — локальний конвертер URL у Guix narinfo. Він не створює ключі, не підписує дані, не збирає package closures і не публікує архіви.

`.github/workflows/substitutes.yml` та `.github/workflows/package-archives.yml` тимчасово залишені як вимкнені декларації наміру. Обидва мають `if: ${{ false }}`, ручний тригер без автоматичного push-тригера, read-only permissions і не виконують жодної build/export/deploy дії.

## Рішення, яких бракує

**1. Ліцензія та право на розповсюдження — issue #367.**

Потрібне окреме рішення власника щодо суперечності між repository license declaration та Guix package metadata, а також щодо права розповсюджувати отримані package outputs/NARs. Поки issue #367 відкрите, не запускайте package archive workflow, не прикріплюйте NAR до Releases/Actions artifacts і не вмикайте substitute workflow.

**2. Channel trust — issue #534 / Phase B.**

Потрібні owner-signed introduction/history, `.guix-authorizations`, публічний keyring та успішна перевірка звичайним `guix git authenticate` consumer. Не використовуйте `--disable-authentication`, вигаданий fingerprint або рухому гілку як production source.

**3. Endpoint і ключ.**

Власник має зафіксувати українською в ADR:
- точні URLs metadata та NAR assets;
- хто генерує і зберігає private key, де він використовується, хто має доступ;
- ротацію, відкликання та процедуру компрометації;
- дозволений trigger (manual/tag/release) та хто його запускає;
- retention, доступність, ліміти й процес видалення старих assets.

GitHub Releases та Pages були названі допустимими hosting families, але це не затверджує конкретний endpoint, signing key custody або право розповсюджувати WSM builds.

## Поточна схема — лише варіант для майбутнього рішення

Можлива архітектура після owner approval: підписані Guix narinfo як metadata + NAR archives як окремі immutable assets. Вона не повинна запускатися автоматично від push у `main`.

Підпис Guix narinfo охоплює ідентичність store object (StorePath, NarHash, NarSize, References та Deriver, якщо присутній), а транспортний URL можна переписати лише якщо це підтверджено конкретним pinned Guix форматом і тестами. Converter має зберігати всі підписані поля байт-у-байт та відмовлятися від неоднозначних/multi-URL форматів, які він не підтримує.

До окремої перевірки pinned Guix не припускайте, що compression layout, ім'я NAR asset, location `signing-key.pub` або cache warm-up збігаються з поточним upstream manual.

## Що дозволено робити до рішення

- статично перевіряти Scheme/Python код, YAML і тестові fixtures;
- звіряти очікуваний формат із pinned Guix source;
- складати release manifest без package output binaries;
- документувати trust, ownership, provenance та acceptance gates.

Не створюйте signing keys, не додавайте secrets, не запускайте package build/export, не створюйте GitHub Release assets, не викладайте Pages metadata і не вмикайте workflow guards до явного owner approval українською.

## Статус

Жоден substitute cache не опублікований цією роботою. Наявність workflow чи конвертера не означає, що канал автентифіковано, package build пройшов або бінарний output дозволено розповсюджувати.
