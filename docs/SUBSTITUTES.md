# H170 Free — субститути Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Workflow: `.github/workflows/substitutes.yml`
- Маніфест пакетів: `drivers/profiles/h170-free-packages.scm`
- Lock Guix: `channels.lock.scm` (лише офіційний канал Guix)
- Стан публікації: workflow налаштований; успішної публікації H170 Free cache поки не зафіксовано
- Зберігання: незмінні assets GitHub Release для NAR; GitHub Pages для `.narinfo`, `nix-cache-info` та `signing-key.pub`

## Перший набір пакетів

Початковий H170 Free cache містить рівно 11 upstream-пакетів із фіксованого маніфесту:

- `linux-libre`
- `mesa`
- `vulkan-loader`
- `vulkan-tools`
- `pciutils`
- `usbutils`
- `alsa-utils`
- `ethtool`
- `nvme-cli`
- `smartmontools`
- `lm-sensors`

Набір резолвиться через `guix time-machine -C channels.lock.scm`; він не залежить від рухомої ревізії Guix або неперевіреного списку назв пакетів із workflow input. Workflow збирає маніфест, доручає `guix publish` підписати й кешувати NAR, зберігає NAR-файли як assets GitHub Release та розгортає перетворені метадані `.narinfo` на Pages.

Це відтворювана upstream-основа для H170, а не заява про сертифіковану апаратну сумісність чи оптимізоване ядро. У наборі немає WSM-owned пакетів, входів Nonguix, пропрієтарного NVIDIA-драйвера або firmware blob. Зокрема, цей набір не підтверджує 3D/compute для GTX 1050 Ti.

## Що не входить до цього потоку

- `wsm-tools`, `wsm-live-tools` та Compatibility live tools не входять до публічного кешу, доки не вирішено issue [#367](https://github.com/juv4uk/wsm-desktop/issues/367). Цей issue **не** блокує upstream-only набір.
- Прошивка NVIDIA GP107 виключена. Тому issue [#586](https://github.com/juv4uk/wsm-desktop/issues/586) не є передумовою для цього набору.
- Phase B автентифікації WSM-каналу окремий від цього кешу: результати збираються з офіційного Guix lock, а не з WSM-owned модулів каналу. Phase B лишається обов'язковою перед тим, як просити користувачів довіряти або фіксувати віддалені ревізії WSM-owned каналу, наприклад майбутній пакет `linux-libre-h170`.
- Nouveau atomic-KMS overlay у PR [#767](https://github.com/juv4uk/wsm-desktop/pull/767) — окремий кандидат. Він має пройти Scheme evaluation на точному lock і повну збірку ядра, перш ніж потрапити до майбутнього маніфесту кешу.

## Налаштування ключа підпису

Субститути Guix підписуються. Workflow відмовляється від публікації, якщо owner-controlled пара ключів не налаштована.

На машині власника з Guix:

```sh
sudo guix archive --generate-key
gh secret set GUIX_SIGNING_KEY --repo juv4uk/wsm-desktop < /etc/guix/signing-key.sec
gh variable set GUIX_SIGNING_PUBLIC_KEY --repo juv4uk/wsm-desktop < /etc/guix/signing-key.pub
```

Приватний ключ зберігається лише як GitHub Actions secret `GUIX_SIGNING_KEY`; відкритий ключ — як repository Actions variable `GUIX_SIGNING_PUBLIC_KEY`. Не комітьте жоден із ключів і не вставляйте приватний ключ в issue, чат чи журнали workflow. Публічний ключ публікується разом із метаданими, щоб клієнти могли авторизувати його після перевірки provenance конкретного першого релізу.

Новий незмінний cache release має назву `h170-free-cache-<workflow-run-number>`. Workflow запускається після злиття релевантних змін у `main` або вручну з `main`; довільний список пакетів через workflow input не приймається.

## Довіра клієнта

Після успішної публікації візьміть Pages URL і release tag зі звіту Actions. Авторизуйте опублікований публічний ключ:

```sh
curl -fsS <PAGES_URL>/signing-key.pub | sudo guix archive --authorize
```

Потім додайте Pages URL до `--substitute-urls` демона поряд з офіційними серверами Guix. Не авторизуйте ключ лише тому, що файл доступний за URL: спочатку звірте його з публічним ключем, зафіксованим у provenance конкретного релізу.

## Межі доказів

Успішний workflow підтверджує derivations пакетів, створення підписаних NAR, завантаження assets у Release та розгортання метаданих Pages для зафіксованого маніфесту. Він не підтверджує:

- прив'язку драйверів під час виконання на платі H170 власника;
- завантаження firmware або фізичну роботу GPU;
- завантаження BIOS/UEFI, роботу інсталятора чи зміни диска;
- GP107 3D/compute, reclocking або повну продуктивність;
- доступність окремого WSM-owned каналу чи його автентифікованого ланцюжка Phase B.

ISO, NAR та інші результати збірки не комітяться у звичайні Git-гілки.


## Окрема публікація NAR closure без довготривалого substitute-ключа

Для фізичної видачі пакетів як окремого перевірюваного bundle додано файл .github/workflows/package-archives.yml. Це не заміна й не прихований обхід substitutes.yml: workflow використовує той самий pinned channels.lock.scm та точний маніфест drivers/profiles/h170-free-packages.scm, але формує незалежний prerelease з повною recursive closure.

- Запуск: явний tag packages-h170-free-* або ручний dispatch із main.
- Пакетний allowlist: усі 11 коренів із маніфесту; workflow читає маніфест як дані й звіряє його з фіксованим allowlist, а не виконує довільні package expressions.
- Provenance: Guix .drv, store path, recursive NAR hash, сирі guix show recutils записи з effective license, pinned channel description, lock/manifest hashes і closure-size report.
- Підпис NAR: одноразова пара Guix archive keys створюється на ephemeral runner до запуску daemon. У prerelease включається лише відкритий ключ; приватний ключ не експортується й не стає довготривалим GitHub secret.
- Цілісність: recursive NAR bundle стискається, розбивається на менші assets, отримує GitHub build provenance attestation; workflow завантажує релізні assets назад і перевіряє SHA256 та zstd.
- Зберігання: окремий versioned GitHub prerelease. Бінарні дані не потрапляють до звичайних Git-гілок.

Імпорт конкретного bundle після перевірки його provenance:

    sha256sum -c SHA256SUMS
    sudo guix archive --authorize < signing-key.pub
    cat h170-free-closure.nar.zst.part-* | zstd -dc | guix archive --import

Ключ є короткоживучим ключем конкретної збірки. Його авторизація стосується саме цього релізу; не переносіть її на невідомі майбутні релізи без перевірки нового provenance.

## Поточні результати автоматизації

substitutes.yml (довготривалий HTTP substitute cache із GitHub Pages) і package-archives.yml (окремий prerelease bundle) мають різні ключові моделі. На 2026-11-28 run 46115320185 для substitutes.yml завершився помилкою на кроці Validate owner-controlled substitute signing keys: GUIX_SIGNING_KEY і GUIX_SIGNING_PUBLIC_KEY не задані, тому оцінювання та збірка 11 пакетів були пропущені. Це не свідчить про помилку пакетів і не є успішною публікацією.

Довготривалий substitute endpoint потребує owner-controlled key custody та окремого налаштування GitHub secret/variable. Перший package prerelease може бути зібраний незалежно з одноразовим ключем; це дозволяє розповсюдити перевірювану closure, але не створює постійного сервера субститутів.
