# Проєктування інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

> Цей документ описує початковий Guix-oriented deployment design. Nix/NixOS backend потребуватиме окремого adapter design; Guix-specific кроки не можна переносити до нього.

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
5. Розмітка диска та монтування перевіреним модулем Calamares.
6. WSM configuration summary: диск, partition plan, mount points, profile, boot mode.
7. Явне підтвердження незворотних дій.
8. WSM preflight.
9. Генерація конфігурації Guix.
10. Guix system build / перевірка конфігурації.
11. Guix system init.
12. Перевірка завершення та звіт.

Порядок буде уточнено після тестування обраної версії Calamares та її модулів.

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
