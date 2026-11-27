# Адаптація практик Omarchy для WSM Desktop

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: дослідження завершено на рівні upstream/source audit; runtime/build validation не виконано.
- Issue: [#530](https://github.com/juv4uk/wsm-desktop/issues/530).
- Дата перевірки: 2026-11-27.
- Omarchy source snapshot: [`omacom/omarchy` commit `c56cbe9235d9eea93d4963283effca5b980e40ef`](https://github.com/omacom/omarchy/commit/c56cbe9235d9eea93d4963283effca5b980e40ef).
- Guix source snapshot: [`guix-mirror/guix` commit `4e5195be20d9b124df8a8bb69213412236e4668e`](https://github.com/guix-mirror/guix/commit/4e5195be20d9b124df8a8bb69213412236e4668e), той самий commit, що зафіксований у `channels.lock.scm`.

## 1. Висновок

**Не переносити Omarchy як desktop stack. Перенести її продуктові принципи та вибрані UX-практики на вже обраний KDE Plasma 6.**

Omarchy реалізує інтегрований desktop shell на одному довгоживучому процесі Quickshell: панель, меню, панелі швидких дій, overlays, сповіщення, OSD, lock screen та plugins. Це цілісний продукт, але його архітектура не є автоматично кращою за KDE і не повинна ставати другим shell у WSM.

У pinned Guix source вже є KDE Plasma 6.5.5, KWin 6.5.5, KScreen 6.5.5, Breeze 6.5.5, System Settings 6.5.5, KRunner Frameworks 6.24.0 та Guix service `plasma-desktop-service-type`. Тому найкоротший і найменш ризиковий шлях — використати Plasma як базову оболонку, а WSM-компоненти додавати лише для чітко доведених прогалин.

Цей висновок узгоджується з #169/#170: перший desktop target — KDE Plasma 6, backend — GNU Guix, інсталятор — власний WSM frontend. Документ не змінює ці рішення.

## 2. Межі доказів

| Рівень | Що підтверджено | Чого це НЕ доводить |
| --- | --- | --- |
| Omarchy source | Код і документація з конкретного commit; описані shell, plugins, themes та migrations | Що кожна функція безпомилкова або потрібна WSM |
| KDE documentation | Наявні модулі й описані користувацькі можливості Plasma | Поведінку конкретного WSM build чи Guix package closure |
| Guix pinned source | Пакети та service type оголошені у точній ревізії з WSM lock | Успішний evaluation/build, розмір closure, boot або роботу сесії |
| Runtime / QEMU | Не виконано в межах цього дослідження | Не можна заявляти про працездатний desktop ISO |
| Фізичні монітори та H170 | Не тестувалися | Не можна заявляти про підтверджену багатомоніторність чи H170 acceptance |

Відсутність runtime evidence позначається як **не перевірено**, а не як успіх чи несумісність.

## 3. Матриця адаптації

| Можливість Omarchy | Що вже є в KDE Plasma | Рішення WSM |
| --- | --- | --- |
| Єдина тема для оболонки та програм | Global Theme, Plasma Style, Application Style, Colors, Fonts, Icons, Cursors; Breeze і Breeze GTK | **Налаштувати upstream.** Визначити один WSM appearance profile, не створювати власний theme engine |
| Панель, системне меню, launcher | Plasma panels/widgets, Application Launcher, KRunner | **Повторно використати.** Не переносити Quickshell bar/menu |
| Швидкий пошук і клавіатурний запуск | KRunner: запуск програм, пошук, обчислення, desktop actions, plugin runners | **Повторно використати.** Перевірити й налаштувати keyboard-first workflow |
| Робочі простори | KWin Virtual Desktops, Activities, Desktop Grid, window rules | **Налаштувати й перевірити.** Не ототожнювати Activities з незалежними per-monitor workspaces |
| Незалежні простори на кожному моніторі | Plasma/KWin мають virtual desktops і screen-aware window management; повна семантика Omarchy не доведена як еквівалент | **Runtime spike після першого ISO.** Перевірити KWin на двох/трьох дисплеях; не писати власний compositor |
| Тайловий / floating / scrolling layout на робочий простір | KWin має window rules, scripts та кілька режимів керування вікнами; точний parity з Omarchy не встановлений | **Відкласти.** Спершу оцінити KWin scripts та upstream extensions; не додавати Hyprland |
| Сповіщення, історія, Do Not Disturb | Plasma notifications: history, per-app policy, DND, автоматичне DND під час screen sharing/fullscreen/mirroring, critical notifications | **Повторно використати.** Додаткове групування/snooze оцінити окремо за поведінковими тестами |
| Control Center | KDE System Settings уже має Appearance, Workspace, Personalization, Network, Hardware та System Administration modules | **Не дублювати.** WSM додає тільки hardware evidence view і навігацію до відповідних KDE modules |
| Панелі аудіо/мережі/Bluetooth/живлення/дисплеїв | Plasma applets та System Settings modules, NetworkManager/PipeWire integration | **Повторно використати.** Власні контролери не створювати без доведеної прогалини |
| AI/agent status у панелі | Omarchy має agents widget/panel та інтеграцію з локальними моделями; це UI/інтеграція, не доказ безпечного sandbox | **Відкласти окремим напрямом.** WSM Agent Hub не повинен бути Quickshell plugin або root-capable shell wrapper |
| Plugin ecosystem | Omarchy має manifest-based QML plugins у спільному Quickshell process | **Не переносити runtime.** Capability facade не є процесною ізоляцією; WSM extensions мають мати явний trust model |
| Міграції user config | Omarchy має per-user idempotent migrations із completion state у user state directory | **Перенести принцип.** Не переносити shell scripts; у WSM мігрувати тільки WSM-owned versioned user data, з backup і tests |
| Event-driven updates | Omarchy рекомендує native signals/IPC/file watch замість polling per widget | **Перенести принцип.** Нові WSM status surfaces мають спільний event source; polling — лише обґрунтований fallback |
| Інсталятор та образи | Omarchy має власні Arch package/install assumptions | **Не переносити механізм.** Залишити Guix live image та WSM installer contracts #13/#169/#170 |
| Профілі програм | Omarchy defaults/menus і Arch packages | **Guix-native профілі вже мають власника #149.** Не створювати другий package manager |

## 4. Що саме Omarchy робить добре

### 4.1 Цілісність оформлення

Omarchy theme впливає не лише на шпалеру: upstream описує спільний вигляд desktop, terminal, Neovim, activity screen, Chromium та shell surfaces — bar, menu, notifications, OSD і lock screen. У shell є семантичні токени кольору, типографіки, spacing, control states та motion.

Це сильний продуктовий принцип: користувач обирає тему, а не налаштовує десяток несумісних компонентів вручну.

**Адаптація WSM:** один версіонований appearance profile, який налаштовує штатні механізми Plasma/Qt/GTK та підтримувані application themes. Не гарантувати, що кожна стороння програма автоматично прийме тему. Профіль повинен мати безпечний fallback на Breeze, не переписувати довільні user configs і не встановлювати сторонні теми/плагіни автоматично.

### 4.2 Launcher і клавіатурна навігація

KRunner уже виконує роль універсального keyboard-first entry point: запуск програм, пошук, обчислення, web/bookmark search, desktop actions та розширення через runners. Це значною мірою закриває потребу в окремому Omarchy-style launcher.

**Адаптація WSM:** зафіксувати рекомендовані гарячі клавіші, налаштувати KRunner runners і перевірити український ввід, focus behavior та доступність. Власний launcher не створювати, доки тестами не доведено конкретну UX-прогалину.

### 4.3 Робочі простори та дисплеї

Omarchy описує окремі набори workspaces на кожному моніторі, перемикання в контексті активного дисплея та запам'ятовування наборів після повторного підключення монітора. KDE має KWin virtual desktops, Activities, screen-aware task switching і KScreen.

Це не означає, що моделі ідентичні. Plasma Activities групують desktop containments/widgets, тоді як virtual desktops організують вікна. Не можна називати Activities еквівалентом per-monitor workspace sets.

**Адаптація WSM:** не писати compositor чи window manager. Після #170 зробити вузький runtime spike:
- один монітор, два монітори, три монітори;
- різні роздільності, scaling та orientation;
- unplug/replug і зміна primary display;
- переміщення вікна між дисплеями;
- відновлення virtual desktop після logout/login;
- keyboard-only navigation;
- Wayland session, а X11 — лише якщо він реально входить у підтримуваний профіль.

Поки ці сценарії не перевірені, per-monitor behavior має статус unknown.

### 4.4 Сповіщення

Plasma вже має DND, історію, налаштування per-app/per-service, critical notifications і автоматичне вмикання DND для screen mirroring, screen sharing та fullscreen applications. Omarchy демонструє цікаві UX-практики: групування за sender, snooze, history та inline actions.

**Адаптація WSM:** залишити Plasma Notification Manager. На точному Guix build перевірити:
- чи групуються повторювані повідомлення передбачувано;
- чи можна без втрати змісту відкласти/прибрати повідомлення;
- чи зберігається історія після logout/reboot у межах очікуваної політики;
- чи доступні keyboard actions і screen-reader labels;
- чи critical notifications не губляться в DND.

Не замінювати notification daemon лише заради візуальної схожості. Upstream Omarchy мала публічне повідомлення про регресію групування після заміни notification backend; це аргумент за regression tests, а не доказ, що її реалізація загалом непридатна.

### 4.5 Control Center та hardware evidence

KDE System Settings уже розділяє appearance, workspace, personalization, network, hardware та system administration. У WSM немає сенсу повторно реалізовувати керування моніторами, мережею, аудіо, Bluetooth, клавіатурою чи живленням.

**Адаптація WSM:** окремий read-only Hardware Overview (#532) показує:
- пристрій і його точний identity;
- джерело та час спостереження;
- driver candidate / module availability / actual binding як різні факти;
- firmware presence/load/error як окремі факти;
- функціональні тести й їхній scope;
- unknown/not-tested та відомі обмеження.

Зміни конфігурації залишаються в upstream KDE settings або відповідному Guix-owned workflow. Hardware Overview не стає другим system settings backend і не показує один глобальний «compatibility score».

### 4.6 Agent UI та plugins: важливий security boundary

Omarchy має agent panel та plugin registry з manifest/schema. Однак upstream прямо попереджає: third-party QML plugins виконуються в тому самому процесі Quickshell; capability-scoped facades — це API boundaries, а не справжня same-process sandbox. Код плагіна має user-level доступ до файлів і процесів користувача.

Це принципово важливо для WSM. **Не переносити Quickshell plugin runtime і не вважати manifest або capability facade межею безпеки.**

Для майбутнього WSM Agent Hub рекомендована модель:
1. UI — окремий непривілейований клієнт.
2. Агент — окремий процес/ізольоване середовище з мінімальними дозволами.
3. Системні дії — лише через типізований, allow-listed API.
4. Кожна мутація має preview, явне підтвердження, журнал та можливість відмови.
5. Root/system backend не передає агенту довільний shell.
6. Плагіни UI за замовчуванням не отримують доступ до файлової системи, секретів або authentication objects.

У межах #530 це threat-model recommendation; реалізація Agent Hub не входить у scope.

### 4.7 Міграції та стан користувача

Omarchy окремо реалізує per-user migrations: кожна має бути idempotent, стан виконання зберігається для кожного користувача, а machine-wide repairs не повинні повторно ламати систему. Це корисно, бо пакетне оновлення саме по собі не мігрує формати user data.

Guix generations керують системними поколіннями, але не замінюють міграцію файлів і форматів у HOME.

**Адаптація WSM:** зараз не створювати migration runner. Коли з'явиться перший WSM-owned user config format:
- versioned schema;
- явна migration chain;
- per-user completion state;
- backup перед зміною;
- idempotency та interrupted-run tests;
- невідома версія — fail safely, не переписувати файл;
- жодних shell migrations із конкатенацією command strings.

### 4.8 Event-driven UI замість постійного polling

Omarchy shell guide рекомендує використовувати native service signals, IPC events, file watches та push refresh. Таймер у кожному віджеті множить процеси й навантаження на кількість моніторів; polling лишається останнім засобом.

**Адаптація WSM:** якщо з'являться власні hardware/status indicators, вони мають підписуватися на спільний event source або читати актуальний snapshot. Не запускати privileged probe на кожному tick. Для polling потрібні виміряний інтервал, один shared worker, bounded timeout і пояснення, чому немає event source.

## 5. Guix: що перевірено на точному lock

У `channels.lock.scm` зафіксовано Guix commit:

`4e5195be20d9b124df8a8bb69213412236e4668e`

На цій ревізії у вихідному коді Guix знайдено такі package definitions:

| Пакет / service | Версія в pinned source | Висновок |
| --- | --- | --- |
| `plasma` meta-package | 6.5.5 (версія походить від Breeze) | Aggregate package; містить значний набір Plasma components |
| `plasma-desktop` | 6.5.5 | Є definition |
| `plasma-workspace` | 6.5.5 | Є definition |
| `kwin` | 6.5.5 | Є definition |
| `kscreen` | 6.5.5 | Є definition |
| `breeze`, `breeze-gtk` | 6.5.5 | Є definitions |
| `system-settings` | 6.5.5 | Є definition |
| `plasma-systemmonitor` | 6.5.5 | Є definition |
| `krunner` | KDE Frameworks 6.24.0 | Є definition |
| `plasma-desktop-service-type` | Guix service | Є у `gnu/services/desktop.scm` |

Посилання на точні джерела:
- [Guix KDE Plasma packages at pinned commit](https://github.com/guix-mirror/guix/blob/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/kde-plasma.scm)
- [Guix KDE Frameworks packages at pinned commit](https://github.com/guix-mirror/guix/blob/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/packages/kde-frameworks.scm)
- [Guix desktop services at pinned commit](https://github.com/guix-mirror/guix/blob/4e5195be20d9b124df8a8bb69213412236e4668e/gnu/services/desktop.scm)

У визначенні `plasma-desktop-service-type` видно інтеграцію з polkit, system D-Bus, PAM, udev та system profile. Meta-package `plasma` оголошений як пакет, який використовує цей service type; отже, перевага — застосувати штатний Guix service, а не вручну збирати частини desktop із випадкового списку.

**Що не перевірено:** Guix evaluation, package closure, успішний build, SDDM/login, Wayland session, hardware acceleration, audio/network applets, system settings runtime та ISO boot. Package definition означає лише наявність рецепта у pinned source.

Мінімальна наступна перевірка має відбуватися в роботі #170 на disposable QEMU image із `guix time-machine -C channels.lock.scm`. Не створювати окремий Guix channel або substitute trust для Omarchy.

## 6. Рекомендована конфігурація WSM

### Перший ISO — не розширювати scope

- Дотримуватися #170 та існуючого Guix Plasma service path.
- Використати pinned `plasma` meta-package/service та лише додаткові компоненти, необхідні для перевіреного live workflow.
- Перевірити SDDM, Wayland session, terminal, file manager, System Settings, network/audio basics та українську локаль.
- Стартувати з upstream Breeze/стандартного Plasma look; не додавати Quickshell, сторонні теми чи новий plugin runtime.
- Installer лишається WSM-owned frontend за #13; його system actions не обходять Guix backend.
- Closure size, boot/login evidence та список фізичних тестів зафіксувати у #170.

### Після першого ISO

1. Appearance profile (#531): узгоджений WSM вигляд на базі Plasma settings.
2. Hardware Overview (#532): read-only evidence surface поверх чинної schema/collector.
3. Multi-monitor UX spike: перевірка KWin/KScreen, без власного compositor.
4. Notification behavior tests: перевірити фактичну поведінку pinned Plasma.
5. Agent Hub design: окрема задача лише після визначення process isolation, permission model та API contracts.
6. User-data migrations: відкласти до появи реального versioned WSM user artifact.

## 7. Ризики та запобіжники

| Ризик | Запобіжник |
| --- | --- |
| Дублювання Plasma функцій власним shell | Будь-який власний UI має довести upstream gap |
| QML plugin виконує довільний код у довгоживучому процесі | Не вважати same-process facade sandbox; не переносити plugin runtime |
| Memory leak або notification regression у custom shell | Не додавати custom shell; behavior tests для вибраних Plasma функцій |
| Theme/plugin із невідомого git repo | Не встановлювати автоматично; provenance, license, code review |
| Перезапис user settings | Не змінювати файли, які належать користувачу; декларативний профіль з opt-in та fallback |
| Помилкові claims про per-monitor workspaces | QEMU multi-head і фізичні display tests окремо |
| Package recipe приймається за готовий desktop | Не заявляти build/boot без exact-head runtime evidence |
| Agent отримує надмірні права | Окремий процес, мінімальні дозволи, typed API, preview/consent/audit |

## 8. Наступні дії та власники

| Пріоритет | Дія | Канонічний власник |
| --- | --- | --- |
| P0 | Завершити bootable Plasma live ISO і перевірити login/session | #169, #170 |
| P1 | Реалізувати власний installer frontend, не змінюючи backend ownership | #13 |
| P1 | Декларативний WSM appearance profile | #531 |
| P1 | Read-only WSM Hardware Overview | #532 |
| P2 | Multi-monitor behavior spike і тестова матриця | Запропонувати вузький issue після runtime в #170 |
| P2 | Agent Hub threat model/API/process isolation | Створити окрему задачу після визначення owner-а |
| P2 | User config migration framework | Відкласти до появи versioned user artifact |
| Existing | Guix Desktop/Developer/Creator profiles | #149 |
| Existing | Performance baseline | #151 |
| Existing | Hardware evidence/certification semantics | #5, #6, #456 |

## 9. Джерела

### Omarchy — зафіксований upstream snapshot

- [Omarchy source commit](https://github.com/omacom/omarchy/commit/c56cbe9235d9eea93d4963283effca5b980e40ef)
- [Omarchy shell architecture, plugins, IPC and trust boundary](https://github.com/omacom/omarchy/blob/c56cbe9235d9eea93d4963283effca5b980e40ef/docs/omarchy-shell.md)
- [Omarchy first-party plugin catalogue](https://github.com/omacom/omarchy/blob/c56cbe9235d9eea93d4963283effca5b980e40ef/shell/plugins/README.md)
- [Omarchy file layout and migration model](https://github.com/omacom/omarchy/blob/c56cbe9235d9eea93d4963283effca5b980e40ef/docs/file-layout.md)
- [Omarchy top bar and panel UX](https://github.com/omacom/omarchy/blob/c56cbe9235d9eea93d4963283effca5b980e40ef/manual/05-the-top-bar.md)
- [Omarchy themes manual](https://omarchy.org/manual/themes/)
- [Omarchy Quickshell development guidance](https://github.com/omacom/omarchy/blob/c56cbe9235d9eea93d4963283effca5b980e40ef/agents/skills/shell-dev.md)
- [Quickshell OOM report #9897](https://github.com/omacom/omarchy/issues/9897) — individual issue report, not proof of universal failure.
- [Notification grouping regression report #10145](https://github.com/omacom/omarchy/issues/10145) — individual regression report, useful as test motivation.

### KDE upstream documentation

- [System Settings modules](https://docs.kde.org/trunk_kf6/en/systemsettings/systemsettings/general.html)
- [KRunner](https://docs.kde.org/stable_kf6/uk/plasma-desktop/plasma-desktop/krunner.html)
- [System Notification Settings](https://docs.kde.org/stable_kf6/en/plasma-workspace/kcontrol/notifications/notifications.pdf)
- [KWin Virtual Desktops](https://docs.kde.org/stable_kf6/en/kwin/kcontrol/desktop/index.html)
- [Plasma Activities](https://docs.kde.org/stable_kf6/en/plasma-desktop/plasma-desktop/activities-interface.html)
- [KWin task switcher and screen filtering](https://docs.kde.org/stable_kf6/en/kwin/kcontrol/kwintabbox/kwintabbox.pdf)

---

**Підсумкове рішення:** Omarchy — референс UX та інженерних практик, не база WSM Desktop. Перший продукт будуємо на Guix + KDE Plasma 6. WSM додає лише власну апаратну доказовість, інтеграцію, безпечні системні контракти та цілісний досвід; не переписує функції, які вже підтримує upstream.
