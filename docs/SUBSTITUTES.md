# H170 Free — субститути Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Workflow: `.github/workflows/substitutes.yml`
- Маніфест пакетів: `drivers/profiles/h170-free-packages.scm`
- Lock Guix: `channels.lock.scm` (лише офіційний канал Guix)
- Стан публікації: workflow налаштований; успішної публікації H170 Free cache поки не зафіксовано
- Зберігання: незмінні assets GitHub Release для NAR; GitHub Pages для `.narinfo`, `nix-cache-info` та `signing-key.pub`

## Перший набір пакетів

Початковий H170 Free cache містить рівно 11 upstream-пакетів із фіксованого маніфесту:

Це число означає специфікації маніфесту, а не кількість store outputs: Guix multi-output пакети можуть додавати окремі `lib`, `doc` або `bin` outputs. Реальний прогін цього самого pinned manifest повернув 15 store outputs для 11 специфікацій. Publisher перевіряє щонайменше 11 outputs і вимагає, щоб кількість створених NAR та narinfo дорівнювала фактичній кількості outputs.

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

## Підписний ключ кешу

Кожен запуск створює окрему пару ключів командою `guix archive --generate-key` на тимчасовій GitHub-hosted VM. Це одноразова ідентичність конкретного cache release, а не постійний ключ WSM.

Приватний `/etc/guix/signing-key.sec` використовується лише на runner для підпису NAR; він не записується в артефакти, Release, Pages, репозиторій або журнали. Після завершення job тимчасова VM видаляється. Відкритий `signing-key.pub` публікується разом із NAR, контрольними сумами й `provenance.json`. GitHub artifact attestation додатково пов'язує ці файли з workflow run та вихідним commit. Guix зберігає ключі у `/etc/guix/signing-key.pub` і `/etc/guix/signing-key.sec`; приватний ключ необхідно тримати в секреті. Джерело: [GNU Guix Reference Manual — `guix archive`](https://guix.gnu.org/manual/en/guix.html#Invoking-guix-archive).

Тому відкритий ключ змінюється з кожним cache release. Перед використанням клієнт має завантажити відповідний Release, перевірити `SHA256SUMS`, provenance та GitHub attestation, порівняти його публічний ключ із `signing-key.pub` у метаданих Pages і лише тоді авторизувати:

```sh
sudo guix archive --authorize < signing-key.pub
```

Цей режим дозволяє опублікувати перший перевірюваний кеш без довготривалого приватного ключа в GitHub Secrets. Він не створює сталу ідентичність substitute-сервера: кожен новий ключ треба перевірити й авторизувати окремо. Не авторизуйте ключ лише тому, що файл доступний за URL. Guix відхиляє імпорт, якщо підпис недійсний або ключ не авторизований. Джерело: [GNU Guix Reference Manual — `guix archive`](https://guix.gnu.org/manual/en/guix.html#Invoking-guix-archive).

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
