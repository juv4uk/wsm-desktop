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

## Сторонній інсталятор Guix System: `guix-install`

Станом на 26.11.2026 існує сторонній інсталятор
[`franzos/guix-install`](https://github.com/franzos/guix-install), який робить
рівно той вертикальний зріз, який WSM будує сам: розмітка → форматування →
монтування → генерація `system.scm` + `channels.scm` → `guix system init`.

Факти з README проєкту (код не читався, тому це опис заявленого, а не
перевіреного):

- Rust, GPL-3.0, pre-1.0, створений 29.04.2026; CLI і GUI (`iced`) поверх тієї
  самої логіки;
- режими `guix`, `nonguix`, `panther`, `enterprise`; `--dry-run` друкує
  згенерований `system.scm` без розмітки;
- вісім фаз, стан зберігається у `/tmp/.guix-install-state` після кожної фази;
  повторний запуск продовжує з невдалої фази;
- у бінарник **вкомпільовані** ключі substitute-серверів (`substitutes.nonguix.org`,
  `substitutes.guix.gofranz.com`).

### Чому це вхідні дані, а не рішення

Три речі в ньому прямо розходяться з принципами WSM, і саме вони роблять його
корисним для оцінки, а не для запозичення:

1. **Вкомпільовані ключі substitute-серверів** — це той самий «канал, про який
   ніхто не знає, звідки він», від якого застерігає
   [LESSONS-FROM-OMARCHY.md](LESSONS-FROM-OMARCHY.md). WSM вимагає явного,
   автентифікованого й названого каналу.
2. **Стан у `/tmp/.guix-install-state`** — передбачуваний шлях у
   world-writable каталозі. Це клас, який Omarchy отримав у вигляді окремого
   виправлення (#7904, передбачуваний `/tmp` authfile). WSM тримає runtime-стан
   у приватному UID-owned каталозі ([RECOVERY.md](RECOVERY.md)).
3. **Rust-реалізація** — суперечить [ADR 0009](decisions/0009-installer-backend-not-rust.md),
   який фіксує Python-бекенд і бере з `distinst` патерн, а не код.

Отже: не форк і не залежність. Це джерело для оцінки в
[#10](https://github.com/juv4uk/wsm-desktop/issues/10)/[#11](https://github.com/juv4uk/wsm-desktop/issues/11):
воно показує, що вісім фаз, resume-on-failure і `--dry-run` — реалістичний обсяг
для одного бінарника, і дає конкретний перелік місць, де «зручно» розходиться з
«безпечно».

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

### KDE Plasma

- Актуальний stable — **Plasma 6.8.3** (10.11.2026); лінія 6.8 була
  оголошена 14.10.2026. Не слід стверджувати, що 6.7 припинила отримувати
  виправлення того самого дня: KDE опублікувала **Plasma 6.7.6** 03.11.2026,
  уже після виходу 6.8.0. Це останній 6.7.x випуск, який видно в офіційному
  каталозі на дату цього зрізу.
- Паралельно підтримується LTS-лінія **6.6**: випуск 6.6.7 датований
  16.10.2026; KDE вказує орієнтовний строк підтримки цієї LTS-лінії до
  серпня 2029 року. Це upstream-статус, а не доказ доступності 6.6.7 у нашому
  Guix lock.
- **Plasma 6.8 прибирає X11 login session.** У менеджері входу доступна
  Wayland-сесія; окремі X11-застосунки продовжують працювати через XWayland.
  Тобто XWayland не є запасною повноцінною Plasma/X11-сесією.
- WSM не вибирає версію Plasma сам: `plasma-desktop-service-type` приходить із
  зафіксованого Guix-зрізу, тому фактична версія — похідна від піна каналу
  ([#39](https://github.com/juv4uk/wsm-desktop/issues/39)). **Відкритий пункт:** перевірити,
  яку саме версію несе поточний пін. Без Guix evaluation/build не можна
  стверджувати ні «у нас 6.8+», ні «у нас LTS».
- Поточний minimal-live напрям WSM — CLI/TUI, а Calamares deprioritized.
  Тому зміна X11/Wayland у Plasma не є підставою повертати Calamares або
  другий frontend. Якщо Plasma desktop буде включено в перевірюваний шлях,
  Wayland стане єдиною сесійною ціллю: display, keyboard/input, GPU та resume
  необхідно перевірити на reference hardware; відсутність X11 fallback не
  можна компенсувати припущенням про сумісність.

### Calamares

- Актуальний stable upstream — **3.4.3** (2026-09-10); деталі provenance,
  checksums і наслідки для packaging spike зібрані в
  [CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md), а не тут.

Джерела:
- [Guix 1.6.0 release meeting notes, 15.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00088.html)
- [Guix toolchain/transition freeze, 10.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00039.html)
- [GCD 009 deliberation notice](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00074.html)
- [Guix repository on Codeberg](https://codeberg.org/guix/guix/)
- [KDE Plasma 6.8.3, 10.11.2026](https://kde.org/announcements/plasma/6/6.8.3/)
- [KDE Plasma 6.8 announcement, 14.10.2026](https://kde.org/announcements/plasma/6/6.8.0/)
- [KDE Plasma 6.7.6, 03.11.2026](https://kde.org/announcements/plasma/6/6.7.6/)
- [KDE Plasma 6.6.7 LTS, 16.10.2026](https://kde.org/announcements/plasma/6/6.6.7/)
- [KDE Plasma LTS support policy](https://kde.org/support/compliance/)
- [Official Plasma source release archive](https://download.kde.org/stable/plasma/)
