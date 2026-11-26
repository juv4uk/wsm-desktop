# Джерела та upstream-документація

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Цей документ фіксує першоджерела, на які спирається архітектура WSM Desktop. Перед релізом потрібно повторно перевіряти документацію та прив'язуватися до конкретних версій/ревізій, а не вважати посилання на рухому гілку незмінним контрактом.

## GNU Guix

- [GNU Guix](https://guix.gnu.org/) — офіційний сайт.
- [GNU Guix Reference Manual](https://guix.gnu.org/manual/en/) — довідник.
- [Invoking guix system](https://guix.gnu.org/manual/en/html_node/Invoking-guix-system.html) — build, init, vm та інші дії guix system.
- [Channels](https://guix.gnu.org/manual/en/html_node/Channels.html) — канали, автентифікація та відтворення.
- [Creating a channel](https://guix.gnu.org/manual/en/html_node/Creating-a-Channel.html) — вимоги до власного каналу та застереження щодо сумісності API.

## Calamares

- [Calamares project](https://calamares.io/) — офіційний сайт.
- [Module authoring documentation](https://github.com/calamares/calamares/blob/calamares/src/modules/README.md) — типи модулів, Python job modules та їхній контракт.
- [Deployment configuration](https://calamares.euroquis.nl/docs/deploy-configuration) — settings.conf та побудова сценарію встановлення.
- [Developer guide](https://calamares.euroquis.nl/docs/develop-code/) — правила розробки та ліцензування.

Calamares API і формат конфігурації потрібно перевіряти саме для тієї версії, яку WSM вирішить пакувати.

## Nonguix

- [Nonguix upstream repository](https://gitlab.com/nonguix/nonguix) — першоджерело каналу.
- [Nonguix GitHub mirror](https://github.com/nonguix/nonguix) — README та огляд проєкту.
- [Nonguix installation instructions](https://github.com/nonguix/nonguix#installation) — channel introduction та fingerprint.

Nonguix є незалежним community channel. Його інструкції містять застереження щодо nonfree software; WSM Compatibility не є офіційним профілем GNU Guix.

## Ліцензії

Робота проєкту поширюється під ліцензією ВОЛЬНІСТЬ — повний текст у
[LICENSE](../LICENSE), пояснення в [LICENSING.md](LICENSING.md).

Сторонні проєкти, перелічені вище, зберігають власні ліцензії. Посилання на
них не є твердженням про сумісність: Guix і Calamares поширюються під
GPL-3.0-or-later, і жодна частина цього репозиторію їх не переліцензовує.

## Правило доказовості

Для кожної версії, пакета, драйвера або firmware у майбутньому hardware manifest потрібно зберігати джерело, точну ревізію, ліцензію та результат перевірки. Сам факт присутності компонента в upstream-репозиторії не підтверджує його сумісність з конкретною конфігурацією чи право включати його до WSM образу.


## Calamares — актуальні джерела

- [Офіційний сайт Calamares](https://calamares.codeberg.page/)
- [Основний upstream repository](https://codeberg.org/Calamares/calamares)
- [Релізний тег v3.4.2](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2)
- [v3.4.2 CMakeLists.txt](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CMakeLists.txt)
- [v3.4.2 CONTRIBUTING.md](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CONTRIBUTING.md)
- [v3.4.2 partition module](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/src/modules/partition/CMakeLists.txt)
- [v3.4.2 KPMcore helper](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CMakeModules/KPMcoreHelper.cmake)
- [Developer guide](https://calamares.codeberg.page/docs/develop-code/)
- [Deployment guide](https://calamares.codeberg.page/docs/deploy-configuration/)

Для джерел та API Calamares використовувати основний Codeberg upstream і релізний тег, а не покладатися на старі GitHub посилання. Інформація про пакетні залежності, що не є частиною тегу, повинна бути окремо позначена як оцінка й перевірена на конкретній ревізії.

Деталі сумісності Guix/Calamares зафіксовані у [CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md).

## Стан upstream на 2026-11-26

Датований зріз, а не постійний контракт. Кожен пункт — вхідні дані для рішення,
не рішення: рішення оформлюється ADR або оновленням канонічного документа теми.

### GNU Guix 1.6.0 у підготовці

- Релізна команда Guix 15.11.2026 оголосила, що major update freeze на `master`
  **заплановано на 26.11.2026**; до цього, з 10.11.2026, на `master` уже діяв
  toolchain/transition freeze. Після заморозки на `master` ідуть лише виправлення
  блокерів і security updates, а решта змін живе в team-гілках.
- Наслідок для [#39](https://github.com/juv4uk/wsm-desktop/issues/39) і
  [#210](https://github.com/juv4uk/wsm-desktop/issues/210): доказом
  відтворюваності лишається **точний commit** у `channels/*.lock.scm`, а не
  «останній master». Період заморозки — зручне вікно, щоб зафіксувати зріз, але
  сам факт заморозки не робить рухому гілку піном. Після виходу 1.6.0 рішення
  «пін до релізу чи на реліз» оформлюється окремо.
- [`GCD 009`](https://codeberg.org/guix/guix-consensus-documents) — пропозиція
  узагальнити bootloader subsystem і ввести Guix Bootspec; deliberation тривала
  13–19.11.2026, результат на 26.11.2026 невідомий. Якщо її приймуть, контракт
  запису bootloader зміниться на боці upstream. Для WSM це аргумент не будувати
  власний формат bootloader-конфігурації: наш інсталятор має викликати штатний
  механізм Guix System, а не писати GRUB/EFI-структури сам.
- Практичний стан на цю дату: `channels/compatibility.lock.scm` пінить Guix
  commit `4e5195be20d9b124df8a8bb69213412236e4668e`, який на Codeberg є верхівкою
  `master` станом на 25.11.2026. Це пін, а не доказ того, що зріз збирається.

### Calamares

- Актуальний stable upstream — **3.4.3** (2026-09-10); деталі provenance,
  checksums і наслідки для packaging spike зібрані в
  [CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md), а не тут.

Джерела:
- [Guix 1.6.0 release meeting notes, 15.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00088.html)
- [Guix toolchain/transition freeze, 10.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00039.html)
- [GCD 009 deliberation notice](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00074.html)
- [Guix repository on Codeberg](https://codeberg.org/guix/guix/)
