# WSM Installer GUI

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

Власний Qt 6 / QML frontend WSM для KDE Plasma live session.

## Поточний зріз

- Власна україномовна навігація: welcome → hardware evidence → storage inventory → configuration draft → review.
- Якщо не передано параметр --report, застосунок запускає локальний read-only collector через python3 -m wsm_hwcheck --compact.
- Звіт перевіряє на schema v1.0.0 на вході та повторно передає наявному wsm_install --preflight --backend guix --dry-run; schema validation і побудова diagnostic-only plan залишаються у Python-пакеті WSM.
- Block-device inventory читається через lsblk --json; застосунок не викликає partitioning, formatting, mounting, bootloader installation або Guix deployment.
- --report PATH дозволяє відкрити локальний тестовий звіт без нового probe.

## Межі

Це GUI shell для read-only preflight, а не готовий інсталятор. Поля hostname, locale, timezone, keyboard і позначка target у першому прототипі є локальною UI-чернеткою; поточний backend plan їх не приймає, тому вони не передаються Guix. APPLY не реалізовано. Не використовувати цей прототип для запису на диски.

Застосунок не завантажує probe в мережу. Тимчасовий JSON-звіт створюється у системному тимчасовому каталозі та видаляється при завершенні процесу.

## Побудова

Guix package module розміщений у wsm/packages/installer-gui.scm. Він очікує Qt 6 Core/Gui/Qml/Quick/QuickControls2 із Qt Declarative, Python та пакет wsm-tools. Точний dependency closure треба перевірити через channels.lock.scm; документ не є доказом успішної збірки або запуску.

Локальний CMake smoke після встановлення Qt 6:

- cmake -S installer/gui -B build/installer-gui
- cmake --build build/installer-gui
- ./build/installer-gui/wsm-installer --help
