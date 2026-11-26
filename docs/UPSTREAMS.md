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
- За планом релізної команди (лист 15.11.2026): тиждень 49 (30.11–06.12) —
  створення й тегування release-гілки; тиждень 50 (07.12–13.12) — hard freeze і
  release candidate; **21.12.2026 — цільова дата фінального релізу**. Це план, а
  не обіцянка, і саме так його треба читати.
- Практичний наслідок для піна каналу: між 30.11 і 21.12 зріз `master` може
  змінюватися під реліз, тому пін, зроблений у цьому вікні, фіксує проміжний
  стан. Вибір «пін до 30.11» чи «пін на тег 1.6.0 після 21.12» — окреме рішення
  з власним ADR, а не побічний ефект релізу Guix.
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

### Bootloader та initramfs: уроки Omarchy 25.11.2026

- **Omarchy розділила boot backend за firmware mode:** нові UEFI-інсталяції переходять на `systemd-boot`, BIOS зберігає Limine; наявні Limine-системи не перемикаються автоматично. Робота винесена у loader-neutral шар для boot, cmdline, kernel rebuild та restore, а не в один набір прямих записів у конфігурацію конкретного loader.
- **Secure Boot не слід вважати вже ввімкненим у Omarchy.** Злиття systemd-boot готує сумісний другий етап для підписаного shim, але на дату цього зрізу потрібні окремі підпис kernel/modules, lockdown і enrollment ключів. Сам факт наявності systemd-boot не є доказом Secure Boot.
- **Повторне використання initramfs має вузьку умову.** Omarchy передає попередньо зібраний initramfs лише для точного kernel/package base і незміненої конфігурації образу. Інші kernel modules, keymap, платформа, shared ESP або будь-які зміни initramfs inputs означають локальну перебудову; за відсутнього/несумісного артефакту використовується штатний builder. Після налаштування boot артефакт видаляється з root image. Upstream вказує приблизно 4 секунди економії на одному конкретному install path; це не універсальна оцінка швидкості.
- **Поточний WSM не має цього loader backend.** `systems/live-minimal.scm` вибирає `grub-efi-bootloader`, `systems/live-compat.scm` — `grub-bootloader`. Розмітка BIOS/UEFI у `wsm_install/partition.py` і кроки ESP у `wsm_install/install_steps.py` є планувальним контрактом; вони не дають права окремо писати Limine/systemd-boot конфігурацію. Guix лишається власником встановлення bootloader через `bootloader-configuration`.
- **Межа Guix:** довідник GNU Guix 1.5.0 документує `grub-bootloader`, `grub-efi-bootloader`, removable/netboot варіанти GRUB, `extlinux-bootloader` та `u-boot-bootloader`; `systemd-boot` і Limine не наведені в цьому переліку. Це не замінює перевірку точного commit з channel lock під час Guix evaluation. До появи підтриманого Guix backend або окремого ратифікованого адаптера WSM не повинен додавати власний shell installer для ESP чи EFI boot entries.
- **Безпечне запозичення initramfs-переваги — Guix-native.** Спочатку виміряти, чи потрібна derivation конкретного initrd уже є в store/substitute closure. Повторне використання допускається лише через той самий Guix derivation та його зафіксовані inputs; Free й Compatibility locks/closures не змішувати. Для Compatibility NVIDIA kernel modules, firmware та module options можуть змінювати initrd, отже Free initramfs не можна вважати взаємозамінним. Жодних ручних копій initramfs на ESP, обхідного unpack/apply або нових substitute trust roots.
- **Висновок для WSM:** запозичуємо loader-neutral архітектурну межу, строгий fallback і точну перевірку inputs; не переносимо Limine/systemd-boot, snapshot restore або initramfs sidecar. Перехід на інший loader потребуватиме окремого ADR, підтримуваного Guix backend, BIOS/UEFI QEMU acceptance, перевірки interrupted update/rollback та окремих physical evidence. До того часу діє поточний GRUB path без змін.

Джерела:
- [Omarchy upstream: systemd-boot, BIOS/Limine split та prebuilt initramfs, 25.11.2026](https://omarchyupstream.com/2026-11-25/)
- [Omarchy: boot through systemd-boot with snapshot boot and restore (#19667)](https://github.com/basecamp/omarchy/pull/19667)
- [Omarchy ISO: install UEFI machines with systemd-boot (#489)](https://github.com/omacom/omarchy-iso/pull/489)
- [Omarchy: let systemd-boot install store a pre-built initramfs (#20196)](https://github.com/basecamp/omarchy/pull/20196)
- [Omarchy ISO: boot systemd-boot installs from a pre-built initramfs (#529)](https://github.com/omacom/omarchy-iso/pull/529)
- [GNU Guix 1.5.0 Manual — Bootloader Configuration](https://guix.gnu.org/manual/1.5.0/en/html_node/Bootloader-Configuration.html)
- [WSM Free channel lock](../channels.lock.scm) і [Compatibility channel lock](../channels/compatibility.lock.scm): обидва фіксують Guix commit `4e5195be20d9b124df8a8bb69213412236e4668e`; Compatibility додатково фіксує окремий Nonguix commit.

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

### Гонка simpledrm → нативний DRM (SDDM #1917)

Це та сама гонка, від якої ми ставимо статичну заборону на `sleep` у
[LESSONS-FROM-OMARCHY.md](LESSONS-FROM-OMARCHY.md) (рядок Omarchy #20059).
Корисно знати механізм, а не лише заборонений засіб.

Симптом: чорний екран із підсвіченим підсвічуванням; на холодному старті
трапляється у 50–75 % випадків, підтверджено і на `amdgpu`, і на `i915`.
Механізм у SDDM 0.21.0: `simpledrm` зникає → у seat0 `CanGraphical` стає false
→ обробник `canGraphicalChanged` викликає `removeSeat()` без grace-періоду →
деструктор `Display` доходить до `Auth::stop()` → `terminate()`,
`waitForFinished(5000)`, `kill()`.

Позиція розробників ядра (dri-devel, 2024-05): лагодити це в userspace — не
виправлення, а обхід. Саме тому в тексту обговорення прямо сказано, що такий
підхід «змушує userspace додавати щось на кшталт `sleep(10)`». Plymouth, до
речі, уникає цього тим, що **не** вважає `simpledrm` KMS-пристроєм за
замовчуванням.

Окрема деталь для нас: у Omarchy (#17471) `sddm.service` впорядкований
`After=plymouth-quit.service`, тому проміжок між виходом Plymouth і першим
модсетом композитора вбудований у граф — і в цей проміжок консоль повертає
кадр із прошивки (логотип виробника). `--retain-splash` сам по собі не
допомагає, бо ніщо ще не володіє дисплеєм.

Що це означає для майбутнього readiness gate: чекати треба не «скільки-то
секунд», а появи нативного конектора — тобто події, а не таймера.

### GCD 009: Guix Bootspec (прийнято; upstream implementation ще не змерджено)

Guix переробляє підсистему завантажувача. Нинішній інтерфейс формально загальний,
але його семантика й потік даних значною мірою сформовані навколо GRUB:
конфігураційні файли, menu entries та відновлення політики bootloader-а
протікають крізь абстракцію. GCD 009 вводить *Guix Bootspec* як версійований
проміжний контракт між реалізованим поколінням системи та інструментами, які
публікують його для конкретного bootloader-а. Ідея — відокремити вимоги
покоління до запуску від політики bootloader-а й deployment environment,
а backend-ам залишити перетворення цього опису у власний формат.

**Результат консенсусу:** deliberation завершилася 18.11.2026. Участь взяли
23 з 83 учасників команди: 7 голосів `I support`, 16 — `I accept`,
0 disapprovals. Автор оголосив GCD прийнятим 20.11.2026. Це вже не draft
без рішення. Водночас Codeberg PR [#15](https://codeberg.org/guix/guix-consensus-documents/pulls/15)
на момент цієї перевірки все ще відкритий і очікує upstream merge; прийняття
консенсусного документа не означає, що реалізація вже потрапила до Guix main.

**Що це означає для WSM:**
- Поточний Guix pin у `channels.lock.scm` —
  `4e5195be20d9b124df8a8bb69213412236e4668e` (25.11.2026). У перевіреному
  `gnu/bootloader.scm` він усе ще експонує GRUB-shaped `bootloader-configuration`
  та `menu-entry` API; в `gnu/system.scm` і `gnu/bootloader.scm` немає
  Bootspec migration. Не приписувати цьому snapshot новий контракт лише тому,
  що GCD вже прийнятий.
- WSM ще не виконує встановлення/оновлення bootloader-а й не керує
  міжпоколінною політикою. Тому зараз не переписуємо installer, не створюємо
  власний Bootspec writer/reader і не додаємо припущень про новий Scheme API:
  точні backend records/procedures залишені upstream implementation-у.
- Тримаємо bootloader boundary ізольованою. Коли Guix implementation потрапить
  до каналу, який ми реально розглядаємо для WSM, окремо перевірити: версію та
  serialization Bootspec, сумісність legacy generations через compatibility
  reader, backend preflight для core/extensions/resources, відокремлення
  bootloader policy від generation history та поведінку `guix system image`
  для несумісної root filesystem.
- До такої перевірки наші profile/installer contracts залишаються прив'язаними
  до фактичного pinned Guix API. GCD — прийнятий upstream direction, але ще не
  runtime/build evidence для WSM.

Джерела: [GCD 009 proposal та статус](https://codeberg.org/guix/guix-consensus-documents/pulls/15),
[офіційний запис про прийняття: 23/83, 7 support, 16 accept, 0 disapprovals
(20.11.2026)](https://codeberg.org/guix/guix-consensus-documents/pulls/15#issuecomment-28116399),
[оголошення початку deliberation](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00074.html).

### GNU Shepherd (init system Guix System)

- Shepherd — це init і менеджер служб Guix System, написаний і конфігурований
  Guile Scheme. Серія 1.0 вийшла в грудні 2024 (перший мажор після 21 року
  ZeroVer), станом на кінець 2025 актуальна лінія — 1.0.x; 1.0 вимагає Guile 3.x.
- Для WSM це не абстракція: наш backend — Guix System, тому Shepherd у нас є
  PID 1, і всі наші служби (SDDM, NetworkManager, plasma) описані через нього.
  Тому поведінка Shepherd — це наша поведінка, зокрема під час завершення роботи.
- **Регресійний клас, який варто знати:** у 1.0.9 виправлено помилку, коли
  `stop`-процедура служби не викликалася, якщо її залежність кидала помилку; у
  Guix System це могло призводити до того, що файлові системи не розмонтовувалися
  коректно. Для інсталятора, який монтує цільові файлові системи під `/mnt`, це
  прямий ризик: незавершене розмонтування — це не «попередження в лозі».
  Фіксуємо як upstream-клас, а не як наш дефект: власного коду, який це ламає,
  у нас немає.
- Дрібниця, корисна для релізної довіри: tarball Shepherd 1.0.0 заявлений як
  bit-for-bit відтворюваний із відповідного git-тегу.

**Точна прив'язка до WSM Guix lock (перевірено 26.11.2026).** У зафіксованому
`channels.lock.scm` коміті Guix
`4e5195be20d9b124df8a8bb69213412236e4668e` вихідний код має такий контракт:

- `gnu/services/shepherd.scm` задає `shepherd-1.0` як стандартне значення
  поля `shepherd` у `shepherd-configuration`;
- `gnu/packages/admin.scm` визначає `shepherd-1.0` версією **1.0.9** та
  джерелом `shepherd-1.0.9.tar.gz`; Guix base32 hash джерела:
  `1mh080060lnycys8yq6kkiy363wif8dsip3nyklgd3a1r22wb274`.

Отже, default system Shepherd у source definitions саме нашого Free lock — 1.0.9.
Це сильніше за твердження «upstream уже має виправлення»: виправлена версія
входить у зафіксований пакетний опис WSM backend-а. Але це **ще не** свідчення,
що конкретний WSM ISO зібраний із цим пакетом або що Shepherd 1.0.9 фактично
завантажився в QEMU/на фізичному ПК. Для цього потрібні окремі Guix closure/build
та runtime boot checks.

Джерела з точного pinned commit:
- [`gnu/services/shepherd.scm` — default `shepherd-1.0`](https://git.savannah.gnu.org/cgit/guix.git/tree/gnu/services/shepherd.scm?id=4e5195be20d9b124df8a8bb69213412236e4668e)
- [`gnu/packages/admin.scm` — Shepherd 1.0.9 package definition](https://git.savannah.gnu.org/cgit/guix.git/tree/gnu/packages/admin.scm?id=4e5195be20d9b124df8a8bb69213412236e4668e)

### UKI і Secure Boot: два факти, які змінюють дизайн

Unified Kernel Image — один PE-файл, у який складені stub, ядро, initramfs і
командний рядок; його підписують цілком для Secure Boot, і systemd-boot знаходить
його в ESP без окремого boot entry. Для WSM це майбутній шлях, а не поточний: ми
не маємо ні UKI, ні власного підписувача.

Два факти, які варто знати **до** того, як хтось почне будувати цей шлях:

1. **Під Secure Boot вбудований `.cmdline` перемагає.** Параметри, передані через
   boot entry або вручну, ігноруються, якщо вони вже є в UKI. Без Secure Boot
   передані параметри, навпаки, перекривають вбудовані. Тобто «додамо `root=` при
   завантаженні» — не універсальне припущення: воно залежить від стану Secure
   Boot, і саме тому наш bootloader-контракт не повинен покладатися на ручні
   параметри.
2. **Оновлення bootloader-а або UKI змінює TPM-вимірювання.** Саме тому Fedora
   зробила окремий мінімальний UKI-only GRUB для конфіденційних VM: кожне
   оновлення завантажувача змінює PCR, і політика атестації, яка чекає стабільних
   значень, ламається. Для нас це означає: якщо колись з'явиться attestation-
   політика, оновлення завантажувача стає подією, а не рутиною.

Обидва факти — вхідні дані для рядка реєстру про boot-артефакти
([LESSONS-FROM-OMARCHY.md](LESSONS-FROM-OMARCHY.md), Omarchy #15435), який зараз
позначений `out-of-scope` саме тому, що власного updater-а й підписувача в нас
немає.

### SBOM із `guix graph`

- З Guix **1.5.0** `guix graph` має бекенди `graphml` і `cyclonedx-json`, тобто
  вміє видавати Software Bill of Materials для замикання пакетів. Для WSM це
  єдиний відомий спосіб отримати SBOM, який сягає аж до bootstrap-бінарників,
  без власного коду.
- Формат — CycloneDX JSON, який читають сканери вразливостей (наприклад
  Dependency-Track). Це доповнює наш `release-manifest.json`, а не замінює
  його: manifest каже «що ми зібрали і з якого коміту», SBOM каже «з чого це
  складається».
- Обмеження, назване автором зміни в upstream: у SBOM поки є лише ім'я й версія
  кожної залежності, чого може не вистачити для точного зіставлення з базою
  вразливостей; а для графів, де вузли — імена файлів у store, версію
  доведеться не виводити взагалі.
- Статус для WSM: **вхідні дані**, не рішення. Додавання SBOM у релізний
  конвеєр — окреме рішення з власним ADR, бо воно змінює склад артефактів і
  те, що ми обіцяємо перевіряти.

### Calamares

- Актуальний stable upstream — **3.4.3** (2026-09-10); деталі provenance,
  checksums і наслідки для packaging spike зібрані в
  [CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md), а не тут.

Джерела:
- [Guix 1.6.0 release meeting notes, 15.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00088.html)
- [Guix toolchain/transition freeze, 10.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00039.html)
- [Guix 1.6.0 release schedule, 15.11.2026](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00091.html)
- [GCD 009 deliberation notice](https://lists.libreplanet.org/archive/html/guix-devel/2026-11/msg00074.html) and [acceptance record](https://codeberg.org/guix/guix-consensus-documents/pulls/15#issuecomment-28116399)
- [Guix repository on Codeberg](https://codeberg.org/guix/guix/)
- [SDDM #1917 — гонка з DRM-драйвером](https://github.com/sddm/sddm/issues/1917)
- [dri-devel: simpledrm і запущені дисплей-сервери](https://lists.freedesktop.org/archives/dri-devel/2024-May/453272.html)
- [GCD 009 — Guix Bootspec (deliberation)](https://codeberg.org/guix/guix-consensus-documents/pulls/15)
- [ArchWiki: Unified kernel image](https://wiki.archlinux.org/title/Unified_kernel_image)
- [LWN: Fedora approves a smaller GRUB (UKI, TPM PCR stability)](https://lwn.net/Articles/1085609/)
- [The Shepherd 1.0.0 released](https://shepherding.services/news/2024/12/the-shepherd-1.0.0-released/)
- [GNU Shepherd 1.0.9 released (fixes the stop/unmount bug)](https://lists.libreplanet.org/archive/html/guix-devel/2025-12/msg00032.html)
- [guix graph: CycloneDX backend, PR #2405](https://codeberg.org/guix/guix/pulls/2405)
- [GNU Guix 1.5.0 release announcement](https://guix.gnu.org/en/blog/2026/gnu-guix-1.5.0-released/)
- [KDE Plasma 6.8.3, 10.11.2026](https://kde.org/announcements/plasma/6/6.8.3/)
- [KDE Plasma 6.8 announcement, 14.10.2026](https://kde.org/announcements/plasma/6/6.8.0/)
- [KDE Plasma 6.7.6, 03.11.2026](https://kde.org/announcements/plasma/6/6.7.6/)
- [KDE Plasma 6.6.7 LTS, 16.10.2026](https://kde.org/announcements/plasma/6/6.6.7/)
- [KDE Plasma LTS support policy](https://kde.org/support/compliance/)
- [Official Plasma source release archive](https://download.kde.org/stable/plasma/)
