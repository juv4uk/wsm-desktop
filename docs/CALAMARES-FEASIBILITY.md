# Оцінка можливості інтеграції Calamares у GNU Guix

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

- Дата перевірки: 2026-11-25
- Розглянута версія: Calamares 3.4.2
- Статус: дослідження джерел; локальна збірка ще не виконувалася
- Рішення: 3.4.2 — кандидат для першого прототипу, не підтверджений release target

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

## Рекомендація

Продовжити з невеликого packaging spike для Calamares 3.4.2 у власному WSM Guix channel. Спершу довести dependency closure і набір модулів. Не починати розробку великого backend, поки не підтверджено, що live-середовище може надійно запускати сам Calamares.

Цей документ не засвідчує фактичної збірки, запуску або сумісності на фізичному обладнанні.
