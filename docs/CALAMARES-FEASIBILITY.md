# Оцінка можливості інтеграції Calamares у GNU Guix

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

## Поточна позиція WSM — 2026-11-26

- Calamares не є обраним frontend для поточного WSM minimal-live RC3. Канонічний напрямок першого preview — **read-only CLI/TUI** поверх preflight → plan → typed Guix handoff; Calamares залишається deprioritized/reference-only до окремого рішення.
- Детальний CMake/Qt/KF6/KPMcore розбір нижче стосується **лише тегу v3.4.2**. Його не можна переносити на v3.4.3 без diff review та повторної перевірки конкретного source tag.
- Calamares 3.4.3 Stable — новіший upstream-кандидат, але не підтверджений Guix build target. Опублікований upstream SHA, Debian repack SHA та hash власного завантаження — різні типи даних; WSM має перевірити саме отримані upstream bytes і підпис.
- Немає доказу, що Calamares 3.4.2 або 3.4.3 зібраний у Guix, що partition module реально встановлено, що Python job API працює в live image або що сценарій пройшов QEMU. Package index і release notes не є build/acceptance evidence.
- Будь-яке повернення до packaging spike потребує окремого перегляду issue #10 та ADR 0008; воно не може непомітно змінити поточний frontend direction або створити другий owner для partitioning, bootloader чи system activation.


- Дата перевірки: 2026-11-26
- Історична версія детального CMake-аналізу: Calamares 3.4.2
- Поточний upstream-кандидат: Calamares 3.4.3 Stable
- Статус: дослідження джерел; локальна Guix-збірка та runtime acceptance не виконувалися
- Рішення: Calamares **deprioritized**, лише умовний reference; не є обраним frontend або release target

## Висновок

Calamares можна розглядати як графічний UI та workflow engine WSM Desktop, але він не надає готової інтеграції для Guix System. WSM повинен забезпечити власну конфігурацію Calamares, live-середовище та backend, що генерує Guix System declaration і запускає штатне розгортання Guix.

Версія 3.4.2 використовує Qt 6 за замовчуванням і має окрему підтримку Python job modules. Ключова вимога до нашого інсталятора — не просто зібрати Calamares, а отримати робочий модуль `partition` з KPMcore та Python API для майбутнього WSM deployment adapter.

**Наразі не підтверджено**, що повний dependency closure Calamares 3.4.2 збирається у поточному GNU Guix. До появи CMake configure log, успішної збірки та перевірки модулів не позначаємо пакет як готовий.

## Першоджерела

Основні технічні висновки зроблено за файлами релізного тегу `v3.4.2`:

- [Calamares 3.4.2 CMakeLists.txt](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CMakeLists.txt)
- [Calamares 3.4.2 CONTRIBUTING.md](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CONTRIBUTING.md)
- [Partition module CMakeLists.txt](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/src/modules/partition/CMakeLists.txt)
- [KPMcore helper](https://codeberg.org/Calamares/calamares/src/tag/v3.4.2/CMakeModules/KPMcoreHelper.cmake)
- [Calamares developer guide](https://calamares.codeberg.page/docs/develop-code/)
- [Calamares deploy guide](https://calamares.codeberg.page/docs/deploy-configuration)

CMakeLists та модульні CMake-файли є точнішим джерелом для тегу 3.4.2, ніж застаріла загальна таблиця залежностей у CONTRIBUTING.md, яка там позначена як інформація для серії 3.3 / вересня 2023 року.

## Вимоги базової Qt 6 збірки

Релізний CMake-файл Calamares 3.4.2 встановлює такі параметри:

| Компонент | Вимога в CMake 3.4.2 |
| --- | --- |
| CMake | мінімум 3.16 |
| Мова | C++17 |
| Qt | Qt 6, мінімум 6.5.0 |
| Qt components | Concurrent, Core, DBus, Gui, LinguistTools, Network, Svg, Widgets |
| Qt Quick | Quick та QuickWidgets, коли ввімкнено QML |
| ECM | пошук ECM від 6.5 |
| KDE Frameworks | KF6 CoreAddons від 6.5 — required |
| YAML | YAMLCPP від 0.5.1 — required |
| Polkit Qt | PolkitQt6-1; required, якщо INSTALL_POLKIT увімкнено |
| Python | Interpreter і Development; за відсутності development headers Python job modules вимикаються |
| Python binding | bundled pybind11 за замовчуванням; Boost.Python потрібен лише при вимкненому WITH_PYBIND11 |
| KCrash | optional; crash reporting можна вимкнути, якщо KDE Crash недоступний |

Qt 5 шлях існує, але він не є початковим вибором WSM: Qt 5.15 і KF5 5.78 — legacy alternative, який має сенс лише за конкретної доведеної потреби.

### Python job modules

CMake 3.4.2 має параметри:

- `WITH_PYTHON` — увімкнення Python modules API;
- `WITH_PYBIND11` — Python binding через bundled pybind11, за замовчуванням ON;
- `WITH_QML` — підтримка QML view modules, за замовчуванням ON.

Для WSM deployment adapter потрібні і `Python Development`, і активний Python modules API. Успішна збірка без цих компонентів не відповідає вимогам проєкту.

### Типи модулів і межа виконання

Upstream Calamares описує три interfaces: `qtplugin` для C++/Qt view- і job-модулів, `python` для job-модулів та `process` для зовнішніх команд. Сам upstream позначає process interface як такий, що не рекомендується для звичайної інтеграції: команда проходить через shell, а автор модуля відповідає за quoting, host/target chroot semantics і привілеї. Python job-модулі мають окремі host/target process helpers із timeout.

Тому, **якщо Calamares буде повторно розглянуто**, WSM preflight має залишатися окремою read-only фазою, а Guix handoff — типізованим Python job або нативним модулем. Не передавати користувацькі значення в shell command string і не дозволяти Calamares generic bootloader/user jobs дублювати власність Guix. Це умова безпечної умовної інтеграції, а не повернення Calamares до статусу основного frontend-а.

Джерело: [Calamares module interfaces and job-module guidance](https://github.com/calamares/calamares/blob/calamares/src/modules/README.md).

### Partition support — обов'язкова функція WSM

У релізному `KPMcoreHelper.cmake` для Qt 6 Calamares шукає KPMcore мінімум **24.01.75**. Додатково потрібні:

- KF6 Config;
- KF6 I18n;
- KF6 WidgetsAddons;
- Qt 6 DBus.

Якщо KPMcore відсутній або неприйнятної версії, Calamares пропускає модуль `partition`. Сам Calamares при цьому може продовжити збірку. Для WSM це означає, що простий успішний build не є достатнім: CI має перевіряти, що partition module справді зібраний і встановлений.

FS resizer також використовує KPMcore; його доступність потрібно фіксувати окремо.

## Попередня звірка з GNU Guix

Поточний пакетний індекс Guix показує наявність основних компонентів Qt/KDE, потрібних для Qt 6 маршруту. У перевірених записах були, зокрема:

- QtBase 6.12.0;
- Extra CMake Modules 6.24.0;
- yaml-cpp 0.9.0;
- KCoreAddons, KCrash, KParts, KPackage та KService серії KDE Frameworks 6;
- KPMcore 26.04.1;
- Parted 3.7;
- Polkit-qt має окремий пакетний запис, але його Qt 6 сумісність у потрібній конфігурації ще не підтверджена.

Це інвентаризація за пакетним індексом і поточними package definitions, а не перевірка derivation closure. Вона **не доводить**, що всі CMake package configs, outputs, variant-и та транзитивні залежності доступні у вибраному каналі Guix і можуть бути зібрані разом.

Попередня звірка показує, що потрібні Qt 6 / KF6 package records є в поточному індексі, включно з `polkit-qt6`. Це знімає початкове припущення про явну відсутність Qt 6 Polkit-пакета, але ще не доводить, що CMake знаходить усі targets в одній узгодженій build environment.

Найважливіші питання для першого Guix packaging spike:

1. Чи збирається KPMcore 26.04.1 разом із Qt 6 та потрібними KF6 компонентами у вибраній ревізії Guix?
2. Чи експортує `polkit-qt6` CMake config package як `PolkitQt6-1` у формі, яку очікує Calamares?
3. Чи доступні KF6 Config, I18n, WidgetsAddons як потрібні CMake targets?
4. Чи можна ввімкнути Python Development та bundled pybind11 у Guix derivation?
5. Чи знаходяться runtime-команди та дані для keyboard, timezone, partitioning і probing у контрольованих store paths?
6. Чи встановлюється та запускається Calamares із потрібними plugin paths, QML imports, translations і Qt platform plugins?

## Орієнтир для першого пакета

Початковий пакет WSM має цілитися в:

- Calamares v3.4.2 із перевіреним source hash;
- Qt 6 route;
- C++17;
- Python job modules ON;
- bundled pybind11 ON;
- QML ON, якщо всі Qt Quick компоненти доступні;
- KPMcore ON — без тихого пропуску partition;
- Polkit integration ON для повноцінного інсталяційного сценарію, поки не прийнято й не протестовано інше безпечне рішення.

Не копіювати NixOS-специфічні патчі без перевірки. Патчі, які прибирають створення користувачів або змінюють LUKS behavior, відображають особливості NixOS installer і не є автоматично правильними для Guix.

## Перевірки приймання пакета

- [ ] Source tag і hash підтверджені.
- [ ] CMake configure завершується без missing required dependencies.
- [ ] Build завершується.
- [ ] Python modules API увімкнено.
- [ ] QML modules доступні, якщо їх залишено увімкненими.
- [ ] `partition` module реально побудований та інстальований.
- [ ] KPMcore integration підтверджена у CMake log.
- [ ] Polkit policy та фактична модель запуску перевірені.
- [ ] Calamares стартує з WSM configuration у disposable VM.
- [ ] Результат тесту зафіксований разом із Guix channel revision та повним build manifest.

## Історична рекомендація (замінена 2026-11-26)

Цей текст відображає попередню оцінку після аналізу Calamares 3.4.2. Він **не є поточним завданням або рішенням**: packaging spike для 3.4.2 не схвалений і не запускався. Поточна позиція WSM наведена на початку документа; Calamares deprioritized, а minimal-live RC3 використовує read-only CLI/TUI поверх спільного handoff contract.

Цей документ не засвідчує фактичної збірки, запуску або сумісності на фізичному обладнанні.

---

## Оновлення upstream provenance — 2026-11-26

Попередній GitHub upstream URL більше не є canonical source: репозиторій
[calamares/calamares на GitHub](https://github.com/calamares/calamares)
архівовано 2025-08-18. Проєкт продовжує розробку на
[Codeberg](https://codeberg.org/Calamares/calamares); офіційний портал і
developer documentation перенесені на
[calamares.codeberg.page](https://calamares.codeberg.page/).

Це **не** означає, що Calamares покинуто. Водночас старий GitHub repository
не можна далі використовувати як джерело для оновлень, issues або нових tags.

### Версії та provenance

- Офіційний сайт описує **3.4.2** як перший реально tagged release після
  переїзду на Codeberg. CMake-аналіз у цьому документі зроблено саме для
  `v3.4.2`; його не слід автоматично приписувати 3.4.3.
- Debian source package **3.4.3-1** (26.10.2026) позначає це як новий upstream
  release. Debian повідомляє upstream tarball
  `calamares_3.4.3.orig.tar.xz`, SHA-256
  `b62832265be9e1b80ab4a0851f28cae28ef6808ae6c4969c5ac0369f748f0c29`,
  і Git-Tag-Info `24d7a168167e7023914c0b4f5507c73380bb35df`,
  fingerprint `c7203c0a920670bf94f00bb1b01d1a72ac8dc9a1`.
  Це метадані, опубліковані Debian у підписаному source-package notice; перед
  використанням у Guix треба незалежно отримати Codeberg tag/tarball, перевірити
  підпис і перерахувати SHA-256 саме з отриманих байтів.
- Сторінка релізів Codeberg показує **v3.4.3 Stable** з датою 2026-09-10, підпис
  `adridg` (GPG key ID `14B6CC381BC256D6`), tarball `calamares-3.4.3.tar.gz`,
  SHA-256 `144cbbf6bdcebfb21685950db4f0777218519df095f62f4aa392f28348110d18`.
  Release notes називають дві зміни, що стосуються нас прямо: набір bugfixes і
  дрібних покращень у `partition` module та виправлення введення з клавіатури
  для QML-модулів під Wayland. Перше — наш обов'язковий модуль, друге — наш
  GUI-шлях; обидва є причиною переоцінити 3.4.2 як baseline.
- SHA-256 upstream tarball (`144cbbf6…`) і Debian `orig.tar.xz` (`b6283226…`)
  **різні**, бо Debian перепаковує джерело. Тому хеш для Guix-рецепта береться
  лише з артефакту, який ми самі завантажили й перевірили, а не з чужого
  package metadata.
- Nixpkgs snapshot, перевірений 17–20.11.2026, ще пакував 3.4.2; bump до 3.4.3
  перебував у черзі. Це корисна ознака package-maintenance lag, але не доказ
  про Guix і не причина копіювати Nix patches.

Джерела:
- [Офіційний Calamares portal і Codeberg migration](https://calamares.codeberg.page/)
- [Codeberg releases: v3.4.3 Stable, 2026-09-10](https://codeberg.org/Calamares/calamares/releases/)
- [Debian #1148139: archive/migration notice та 3.4.3-1 source checksums](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1148139)
- [Debian sid package 3.4.3-1](https://packages.debian.org/unstable/utils/calamares)
- [Nixpkgs Calamares package status](https://maintainermode.org/p/calamares)
- [Legacy GitHub repository — archived](https://github.com/calamares/calamares)

### Що змінюється для WSM

1. **Canonical source — Codeberg.** У новому packaging spike фіксувати Codeberg
   repository, tag/commit, signed source provenance і SHA-256. Не додавати
   GitHub archive як updater remote.
2. **3.4.3 — новий кандидат, не доведений build target.** Поточний CMake/Qt/KF6/
   KPMcore аналіз залишається перевіреним лише для 3.4.2, доки не виконано diff
   review та повторну перевірку CMake options/targets для 3.4.3.
3. **Не переносити NixOS-specific patches.** Debian/Nix package metadata
   допомагає знайти версію й залежності, але Guix повинен мати власний
   derivation і reproducible closure.
4. **ADR 0008 лишається proposed.** До ратифікації потрібні Guix package build,
   Python Development + pybind11 API, фактично встановлений `partition`
   module/KPMcore, `loadmodule` tests, privileged job isolation і disposable
   QEMU acceptance. Наявність upstream release або NixOS integration не є
   доказом жодного з цих WSM gates.

Це оновлення змінює джерело та версійний baseline дослідження, але не
ратифікує Calamares і не змінює обраний для поточного minimal-live RC3
read-only CLI/TUI шлях.
