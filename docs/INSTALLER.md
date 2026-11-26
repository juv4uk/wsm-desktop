# Проєктування інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

> Цей документ описує початковий Guix-oriented deployment design. Nix/NixOS backend потребуватиме окремого adapter design; Guix-specific кроки не можна переносити до нього.

## Чотири frontend-и, один read-only planner

| Вхід | Роль | Поточна межа |
| --- | --- | --- |
| **wsm-install CLI** | основний non-graphical entrypoint | read-only preflight і preview; APPLY вимкнено |
| wsm-install --guided | консольний майстер | вибір диска та preview; немає install callback |
| wsm-install --tui | псевдографічний майстер | клавіатурна навігація і preview; немає install callback |
| Calamares | опційний graphical frontend | Python jobmodule; real deployment не підтверджено, APPLY вимкнено |

Усі чотири frontend-и використовують спільні partition.py та install_steps.py.
executor.py наразі лише формує preview і відхиляє dry_run=False. Жоден
frontend не запускає розмітку, mkfs, mount або guix system init.

### Чому CLI первинний

Графічний інсталятор — це Qt, KDE-стек і кількасот мегабайт пам'яті поверх того,
що вже завантажено. На машині з 4 GB це помітно, на машині з 2 GB — це різниця
між «встановлюється» і «не встановлюється».

Проєкт заявляє залізоорієнтованість. Залізоорієнтованість, яка вимагає
графічного інсталятора, — це залізоорієнтованість для тих, у кого вже є
достатньо заліза.

Тому CLI — не «тимчасово, поки не зробимо Calamares». Це основний шлях.
Calamares лишається як зручність для тих, кому вона потрібна.

### Два образи, не один

| Образ | Що всередині | Для чого |
| --- | --- | --- |
| `systems/live.scm` | KDE Plasma, SDDM, звук, друк | звичайна машина |
| `systems/live-minimal.scm` | консоль, мережа, інструменти WSM | слабке залізо, сервер, відновлення |

Мінімальний образ **не містить** ні графічного середовища, ні Calamares: уся
його суть — обійтися без них. Він несе ті самі інструменти й той самий маркер
`WSM_LIVE_READY`, тож приймання для нього не слабше.

### Чим CLI компенсує відсутність графічного UI

| Ризик графічного майстра | Наша компенсація |
| --- | --- |
| Випадково обрано не той диск | CLI/guided/TUI показує target і повторно просить його шлях лише для preview; це не дозвіл на запис |
| Диск підмінили між планом і записом | **не виявляється**: `--target-size-bytes` — введена оцінка, не прочитана властивість пристрою |
| Помилка посеред розбиття | APPLY вимкнено; жодного кроку запису не запускається |
| «Зелена» галочка на несправному кроці | preview показує argv і намір, але не заявляє, що команда запускалась або postcondition виконано |

## Поточна межа безпеки інсталятора

Усі frontend-и — звичайний CLI, `--guided`, `--tui` та Calamares — завершуються
read-only preview. Спільний `wsm_install.executor.execute()` відхиляє
`dry_run=False` з `execute.apply-disabled`; CLI додатково відхиляє
`--execute` до переходу в будь-який frontend. Guided mode не має кроку
«Install now» і не викликає окремий install callback. TUI також завершується після
preview та не показує «Done» або «Installation finished». Calamares із
`wsmDryRun=false` також отримує відмову від того самого executor.

Тому наведені нижче розділи про розмітку, монтування та Guix handoff описують
архітектурний намір і preview argv, а не можливість виконати інсталяцію.
Жодні `sgdisk`, `mkfs`, `mount` чи `guix system init` цим шляхом не
запускаються. Реальний APPLY вимагатиме окремого reviewed контракту:
immutable typed plan, повторного читання block-device identity, digest-bound
consent, перевіреної Guix tool closure, справжніх postconditions та
destructive acceptance на одноразових QEMU-дисках. Детальніше — у
[EXECUTOR.md](EXECUTOR.md).

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

## Обрана версія для прототипу

Початковий кандидат — **Calamares 3.4.2** (tag `v3.4.2`). До завершення feasibility/build перевірок це кандидат, а не підтримувана чи зафіксована релізна залежність. Деталі — у [оцінці можливості інтеграції](CALAMARES-FEASIBILITY.md).

## Ролі

Calamares — це спільний UI та workflow engine. Він не замінює системний deployment engine обраного backend-а.

Для Guix System WSM додає інтеграцію між даними Calamares та Guix System configuration. Nix/NixOS deployment має бути окремим backend adapter із власним порядком build та activation.

## Модульна модель Calamares

Calamares розрізняє user-visible view modules та job modules. View modules реалізуються як Qt plugin (C++/QML); Python interface призначений для job modules. Python job module має module.desc із назвою скрипта (зазвичай main.py) та функцію run(). Успіх повертає None, помилка — пару рядків із повідомленням і деталями.

Перед реалізацією адаптера потрібно зафіксувати конкретну версію Calamares і перевірити її inline Python API. Не слід програмувати проти випадково знайденого прикладу іншої версії.

## Запропонований workflow

1. Welcome та інформація про статус підтримки.
2. Мова та клавіатура.
3. Часовий пояс.
4. Вибір профілю Free або Compatibility з поясненням наслідків.
5. WSM environment preflight: read-only перевірка tools, Guix, root, mount point, system file, report та ISA.
6. Read-only hardware evidence і перевірка цільового пристрою.
7. Побудова partition layout, filesystem та mount plan як даних; жодних записів.
8. WSM configuration summary: цільовий диск, повний partition diff, mount points, profile, boot mode та provenance evidence.
9. Явне підтвердження, пов'язане з immutable target identity і digest повного плану.
10. Єдиний partition executor виконує розмітку, форматування та mount лише після consent. Цей етап не реалізовано: поточний executor preview-only.
11. Генерація конфігурації Guix із того самого typed plan і перевірка guix system build.
12. guix system init лише після окремого accepted APPLY contract і перевірених postconditions.
13. Перевірка результату та звіт.

Це цільова архітектура, а не твердження про реалізований APPLY. Нині всі frontend-и завершуються на read-only preview; consent gate ще не під'єднана до реального disk executor.

## Що не можна просто взяти зі стандартного Calamares

### Bootloader

Guix configuration має бути єдиним джерелом істини для bootloader. Стандартний Calamares bootloader job не повинен запускатися паралельно, якщо Guix system init встановлює завантажувач сам.

### Users

Стандартний users module не вважається сумісним із Guix System автоматично. Guix user accounts є частиною operating-system declaration. WSM має сформувати декларацію користувачів, обробити пароль через перевірений механізм і не зберігати його у відкритому вигляді.

### Filesystems

План mount points, файлових систем, UUID/labels та EFI System Partition має бути пов'язаний із згенерованою Guix-конфігурацією. Не можна будувати конфігурацію з неперевірених рядків.

## Межі WSM deployment adapter

Майбутній Python job module Calamares, якщо його API та потрібні права доступу підтверджені для вибраної версії, повинен:
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

Python jobmodule wsm_deploy і module.desc уже є в репозиторії, але settings.conf та реальний запуск Calamares не підтверджені. Модуль наразі preview-only: explicit wsmDryRun=false відхиляється, true повертає non-success статус «APPLY disabled». Жодний frontend не має підтримуваного APPLY; див. README у installer/calamares/ та EXECUTOR.md.
