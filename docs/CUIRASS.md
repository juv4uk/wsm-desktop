# Cuirass і публікація збірок WSM

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **Cuirass job source виправляється й перевіряється проти pinned Guix; інстанс не запускався**
- Основні файли: [specifications](../ci/cuirass/specs.scm), [ISO job](../ci/cuirass/images.scm), [service](../ci/cuirass/service.scm)

## Ролі конвеєрів

Cuirass — Guix-native scheduler/evaluator/build coordinator. Він оцінює специфікації каналів, запускає derivation builds через Guix store і зберігає job history. Він не замінює GitHub Actions і сам по собі не є публічним substitute server.

| Що доводимо або публікуємо | Власник |
| --- | --- |
| Канал WSM та його пакети оцінюються на pinned Guix | Cuirass job `wsm-channel` |
| Derivation live ISO створюється для запитаних systems | Cuirass custom job `wsm-live-minimal-image` |
| ISO завантажується у BIOS та UEFI; інсталятор запускається в guest | release workflow із QEMU/OVMF |
| ISO, release manifests, hashes та boot evidence публікуються | GitHub Releases |
| Доступність власних package substitutes | окремий publisher/cache deployment; **ще не налаштовано** |

Не вважати локальний Guix store Cuirass автоматично доступним клієнтам. Для HTTP substitute service потрібні окремий процес/експорт `guix publish` або еквівалентний статичний cache, підписані `.narinfo`, NAR payload та клієнтський trust до public key. Успішний job у Cuirass не означає, що користувач уже може отримати substitute.

## Cuirass job для live ISO

Release workflow збирає `systems/live-minimal.scm` як `--image-type=iso9660`. Custom module `ci/cuirass/images.scm` має відтворювати саме цей derivation path:

- Cuirass передає в custom job аргумент `systems` (множина); використовується upstream `arguments->systems` із `(gnu ci)`.
- `image-with-os iso9660-image` прив’язує той самий WSM OS profile до ISO9660 image record.
- `image->job` із `(gnu ci)` створює Cuirass image job і використовує штатний `system-image` lowering; ім’я формується як `wsm-live-minimal.<system>`.
- Grafting вимкнено для відтворюваних build-farm jobs, як і в upstream Guix image jobs.

Pinned Guix evaluation викликає `cuirass-jobs` з реальним `((systems . ("x86_64-linux")))`, відкриває store, знижує image derivation і перевіряє job name, system та `#:job-type`. Це не збирає важкий ISO payload і не доводить його QEMU boot.

## Канали та межа довіри

Офіційний Guix channel зафіксований за commit із `channels.lock.scm` та має channel introduction. WSM channel у поточній Cuirass service specification посилається на `main`. Це development input, а не owner-authenticated release lock.

До завершення підписаного bootstrap WSM channel (introduction/authorizations) та закріплення точного release commit не використовувати цей job як доказ довіреної release-збірки. Не обходити цей gate через `--disable-authentication`. Окрема Guix profile evaluation у CI перевіряє source API на pinned Guix, але не перевіряє віддалену автентифікацію WSM channel.

## Substitute publication: GitHub Releases і GitHub Pages

Зібрані артефакти не комітити в `main`, release branches чи звичайні feature branches. Вихідні файли, Scheme/Python код, manifests і перевірки залишаються в Git; бінарні результати мають окремі канали публікації:

1. **GitHub Releases** — ISO, release bundles та окремі `guix archive --export` bundles для ручного `guix archive --import`. Це не HTTP substitute server.
2. **GitHub Pages із окремої orphan-гілки `gh-pages`** — можливий статичний endpoint для невеликих NAR cache entries. Це окрема publish job із контрольованою заміною вмісту гілки, без зміни `main`.

Статичний substitute mirror повинен мати сумісні з Guix endpoint-и: `nix-cache-info`, `signing-key.pub`, `<hash>.narinfo` у корені та NAR payload-и за URL, вказаними в `narinfo` (типово `nar/<compression>/<store-basename>`). `.narinfo` має містити валідний підпис саме того ключа, який клієнт явно додав до `authorized-keys`. Не публікувати непідписані metadata, не додавати приватний ключ у Pages і не послаблювати перевірку підпису клієнтом.

### Обмеження Pages

Офіційні ліміти GitHub Pages: опублікований сайт не може перевищувати **1 GB**, soft bandwidth limit — **100 GB на місяць**. Для branch-based публікації кожен NAR ще й є звичайним Git object: GitHub має hard limit **100 MiB на один Git-файл**. Тому `gh-pages` підходить лише для невеликого, allow-listed пакета/closure після виміру кожного NAR і сумарного сайту. Один файл понад 100 MiB не можна розбити на частини без зміни Guix substitute URL/формату; такий output треба виключити з Pages cache або розміщувати на Releases/іншому сумісному сервері. Ліміти та очікувану пропускну здатність потрібно контролювати в publisher.

Перш ніж увімкнути Pages:
- створити окремий signing key для WSM substitute cache; приватний ключ зберігати лише в protected publishing environment/secret, public key версіонувати як безпечний trust anchor;
- збирати лише дозволені WSM-owned packages, не експортувати весь CI store або довільні залежності;
- генерувати NAR і `.narinfo` штатним Guix tooling, перевіряти підписи, URL/path consistency, NAR hash/size та реальний `guix substitute` download у disposable client;
- перевірити сумарний розмір сайту, максимальний розмір окремого Git object і bandwidth budget до force-push;
- публікувати в `gh-pages` лише після всіх перевірок, атомарно замінюючи попередній cache. Не використовувати force-push до `main`.

Це design direction, не заява про готовий сервіс: Pages deploy workflow, signing key та клієнтське приймання поки не створені.

## Запуск Cuirass вручну

Інструкція для окремого Guix build host із PostgreSQL. **Інстанс у межах цього завдання не запускався.**

```sh
sudo -u postgres createdb cuirass

guix shell cuirass postgresql -- \
  cuirass register --specifications=ci/cuirass/specs.scm \
                   --database="dbname=cuirass host=/var/run/postgresql" \
                   --interval=300

guix shell cuirass -- cuirass web \
  --database="dbname=cuirass host=/var/run/postgresql" \
  --port=8081 --listen=localhost
```

Web UI — `http://localhost:8081`. Він не має власної автентифікації; не відкривати його публічно. Для віддаленого доступу потрібні TLS та автентифікований reverse proxy.

`ci/cuirass/service.scm` — service fragment, який включається до `services` build-host конфігурації. Він не є повною конфігурацією окремої машини.

## Межі доказів

- **Не завантажує образ.** У Cuirass немає QEMU/OVMF acceptance step.
- **Не перевіряє інсталятор.** `WSM_INSTALLER_OK` створює QEMU guest у release workflow, не Cuirass.
- **Не автентифікує автоматично WSM channel.** Для цього потрібні owner-signed bootstrap та exact release lock.
- **Не публікує substitute endpoint автоматично.** Потрібен окремий підписаний publisher/cache deployment.
- **Не підтверджує фізичну сумісність H170/GTX 1050 Ti.** Для цього потрібне окреме owner-approved hardware evidence.

Поточний стан чесний: код job/service і pinned Guix evaluation перевіряються в CI; сервер Cuirass, substitute publisher і фізичне приймання заліза ще не запущені.
