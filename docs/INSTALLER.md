# Проєктування інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

> **Поточний шлях minimal-live: read-only CLI/TUI preview.** Live-образ
> запускає `wsm-install-live`, який збирає локальний hardware report і
> відкриває WSM TUI. Guided CLI використовує той самий typed plan/handoff
> contract. Усі entrypoints лишаються preview-only: `--execute` і
> `dry_run=False` відхиляються; успішний preview не означає, що WSM
> встановлено. Остаточний frontend інсталятора ще не ратифікований за #10.
> Calamares — deprioritized/reference-only і не входить до поточного minimal-live шляху.

> Цей документ описує початковий Guix-oriented deployment design. Nix/NixOS backend потребуватиме окремого adapter design; Guix-specific кроки не можна переносити до нього.

## Один typed contract, поточний CLI/TUI шлях

| Поверхня | Статус | Межі |
| --- | --- | --- |
| `wsm-install-live` у minimal-live | **Поточний entrypoint preview** | Створює hardware report і відкриває WSM TUI; APPLY вимкнено |
| `wsm-install` та guided CLI | **Діагностичні/планувальні входи** | Використовують спільні report, typed plan і Guix handoff contracts; не пишуть на диск |
| Calamares | **deprioritized/reference-only** | Не входить до minimal-live образу, не є вибраним frontend і не є підтвердженою Guix-залежністю |

Усі поточні поверхні спираються на спільні hardware report, planning і
typed Guix handoff contracts. Це не означає, що існує завершений installer
або що будь-який frontend має право виконувати план: APPLY наразі вимкнено.

### Чому CLI первинний

Графічний інсталятор — це Qt, KDE-стек і кількасот мегабайт пам'яті поверх того,
що вже завантажено. На машині з 4 GB це помітно, на машині з 2 GB — це різниця
між «встановлюється» і «не встановлюється».

Проєкт заявляє залізоорієнтованість. Залізоорієнтованість, яка вимагає
графічного інсталятора, — це залізоорієнтованість для тих, у кого вже є
достатньо заліза.

Тому CLI/TUI — поточний мінімальний live-шлях, а не тимчасова заміна
Calamares. Потреба в майбутньому графічному frontend-і залишається окремим
рішенням #10; не слід подавати Calamares як уже обраний або доступний варіант.

### Два образи, не один

| Образ | Що всередині | Статус |
| --- | --- | --- |
| `systems/live-minimal.scm` | Консоль, мережа, інструменти WSM, CLI/TUI | Поточна основа minimal-live preview |
| `systems/live.scm` | KDE Plasma, SDDM, звук, друк | Окремий desktop/live напрям; не є доказом готового installer UX |

Мінімальний образ **не містить** ні графічного середовища, ні Calamares: уся
його суть — обійтися без них. Він несе ті самі інструменти й той самий маркер
`WSM_LIVE_READY`, тож приймання для нього не слабше.

### Чим CLI компенсує відсутність графічного UI

| Ризик графічного майстра | Наша компенсація |
| --- | --- |
| Випадково обрано не той диск | підтвердження мусить **назвати** диск; `--yes` не існує |
| Диск підмінили між планом і записом | звірка розміру, дрейф понад 2% — відмова |
| Помилка посеред розбиття | перший збій зупиняє все, кожен крок перевіряється |
| «Зелена» галочка на несправному кроці | перевірка читає систему (`blkid`, `/proc/mounts`), а не код виходу |

## Поточний стан: інсталятор не вибрано

Це головне, що варто знати перед читанням решти документа.

| Питання | Відповідь |
| --- | --- |
| Який інсталятор обрано? | **Жоден.** |
| Calamares? | Відкладено: [ADR 0002](decisions/0002-calamares-as-installer.md), переглянуто [ADR 0006](decisions/0006-hardware-first-installer-frontend.md) |
| Що натомість? | ADR 0006 пропонує власний hardware-first frontend за формою archinstall. Статус — `proposed`, **не ратифіковано** |
| Що вже є кодом? | `wsm-install` (перевірка заліза й чернетка плану, read-only), планувальник розбиття, послідовність кроків, gate доказів |
| Чого немає? | Жодного запису на диск. Жодного встановлення. Жодного підтвердження, що профіль збирається |

Рішення ухвалюється в [#10](https://github.com/juv4uk/wsm-desktop/issues/10). Доти будь-який
рядок нижче — це проєкт, а не чинна архітектура.

## Calamares: лише історичний/умовний reference

Calamares не обраний для поточного minimal-live preview і не входить до
підтверджених release dependencies. Документ [CALAMARES-FEASIBILITY.md](CALAMARES-FEASIBILITY.md)
містить історичний CMake-аналіз 3.4.2 та окрему upstream-оцінку 3.4.3;
жодна з цих версій не доведена як Guix build target. Повторний розгляд
потребуватиме окремого рішення, pinned source/signature/hash, Guix closure,
partition-module acceptance і QEMU перевірки.

## Умовна модель Calamares (не поточний шлях)

Наведені нижче технічні нотатки описують лише можливий майбутній adapter,
якщо його повторно розглянуть у межах #10. Вони не є специфікацією вже
обраного frontend-а, залежністю minimal-live ISO або дозволом на APPLY.

Calamares може виступати UI/workflow engine, але не замінює системний
deployment engine. Для Guix він потребував би окремого adapter; Nix/NixOS
потребував би іншого backend adapter і не входить до першого preview.

## Модульна модель Calamares

Calamares розрізняє user-visible view modules та job modules. View modules реалізуються як Qt plugin (C++/QML); Python interface призначений для job modules. Python job module має module.desc із назвою скрипта (зазвичай main.py) та функцію run(). Успіх повертає None, помилка — пару рядків із повідомленням і деталями.

Перед реалізацією адаптера потрібно зафіксувати конкретну версію Calamares і перевірити її inline Python API. Не слід програмувати проти випадково знайденого прикладу іншої версії.

## Умовний workflow Calamares (не реалізовано)

Наведений нижче історичний ескіз не є поточним user journey або
підтвердженою інсталяційною процедурою. Його не можна публікувати як
інструкцію для користувача або виконувати без окремого ADR та acceptance.

1. Welcome та інформація про статус підтримки.
2. Мова та клавіатура.
3. Часовий пояс.
4. Вибір профілю Free або Compatibility з поясненням наслідків.
5. Розмітка диска та монтування перевіреним модулем Calamares.
6. WSM configuration summary: диск, partition plan, mount points, profile, boot mode.
7. Явне підтвердження незворотних дій.
8. WSM preflight.
9. Генерація конфігурації Guix.
10. Guix system build / перевірка конфігурації.
11. Guix system init.
12. Перевірка завершення та звіт.

## Що не можна просто взяти зі стандартного Calamares

### Bootloader

Guix configuration має бути єдиним джерелом істини для bootloader. Стандартний Calamares bootloader job не повинен запускатися паралельно, якщо Guix system init встановлює завантажувач сам.

### Users

Стандартний users module не вважається сумісним із Guix System автоматично. Guix user accounts є частиною operating-system declaration. WSM має сформувати декларацію користувачів, обробити пароль через перевірений механізм і не зберігати його у відкритому вигляді.

### Filesystems

План mount points, файлових систем, UUID/labels та EFI System Partition має бути пов'язаний із згенерованою Guix-конфігурацією. Не можна будувати конфігурацію з неперевірених рядків.

## Межі WSM deployment adapter

Рекомендована перша форма — Python job module Calamares, якщо її API та потрібні права доступу підтверджені для вибраної версії. Модуль повинен:
- читати лише визначені ключі з Calamares global storage;
- перевіряти, що target root і EFI mount points очікувані;
- відмовлятися працювати з неоднозначним або неповним partition plan;
- генерувати конфігурацію із типізованих даних;
- запускати Guix через офіційний API команд Calamares, а не через shell string concatenation;
- повертати структуровану помилку в разі невдачі;
- не записувати секрети в логи.

Використання os.system(), shell=True або довільної shell-команди, складеної з тексту інтерфейсу, заборонене.

## Обов'язкові можливості збірки

Для WSM prototype потрібні Qt 6, Python job modules API та справжній Calamares `partition` module із KPMcore. Збірка, у якій KPMcore відсутній і partition module пропущений, не проходить критерії WSM, навіть якщо основний executable зібрався.

Потрібно перевірити Qt6 Polkit integration та runtime paths у Guix. Не вимикайте INSTALL_POLKIT для кінцевого образу без окремої перевіреної політики привілеїв і security review.

## Поточний стан

Робочого Calamares settings.conf, module.desc або deployment-коду поки немає. Вони будуть додані після M2, коли ми підтвердимо доступність Calamares, його залежностей та інтерфейс API у цільовому live-середовищі. Див. README у installer/calamares/.

Пов'язані документи:

- [INSTALL-CAPABILITY-MATRIX.md](INSTALL-CAPABILITY-MATRIX.md) — які сценарії встановлення взагалі вважаються перевіреними;
- [INSTALLER-REPORT-FRESHNESS.md](INSTALLER-REPORT-FRESHNESS.md) — коли звіт про залізо належить поточній live-сесії;
- [INSTALLER-QEMU-HARNESS.md](INSTALLER-QEMU-HARNESS.md) — як цей шлях перевіряється в QEMU.
