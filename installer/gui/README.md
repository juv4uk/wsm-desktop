# WSM Installer — PySide6 / Kirigami preview

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

**Стан:** перший vertical slice, лише read-only / diagnostic-only. Це не production installer і не deployment executable.

## Архітектура

- Python domain/core: наявні wsm_hwcheck.collect_report, спільна schema validation з wsm_install.validation, wsm_install.plan.build_plan та wsm_install.guided.list_disks.
- UI: PySide6 + Qt 6 QML + KDE Kirigami 6; один typed QObject controller.
- Guix: єдиний системний backend і джерело майбутньої system configuration; цей GUI slice backend не викликає.
- Minimal-live зберігає легкий CLI/TUI recovery path і не отримує залежність від Qt/PySide6.

## Сторінки

Welcome → апаратні докази → read-only список цілих дисків → review/cancel. Вибір диска існує лише в пам'яті процесу. Перед review повторно читається sysfs identity (path, size, removable, model, vendor); дрейф будь-якого спостереженого поля fail-closed. Це не cryptographic device identity і не дозвіл на подальший APPLY.

Звіт перевіряється тією самою версійованою JSON Schema, що й CLI. GUI показує точні unknown/not-detected стани, не виводячи з них працездатність. Звіт старший за 10 хвилин або з недопустимим майбутнім timestamp відхиляється. Діагностичний план будується спільною функцією та показує SHA-256 точних source bytes і plan digest.

## Безпекові межі

- Колектор запускається in-process з include_runtime_diagnostics=False; він читає лише sysfs/procfs.
- Диски перелічуються існуючим read-only list_disks provider через sysfs.
- Жодного subprocess, QProcess, shell, root helper, /dev open/write, mount, partition, format, firmware download, module load, guix system init або APPLY.
- --smoke-test завантажує QML і завершується без hardware collection.
- Package definition (якщо буде прийнята) не включається до default live profiles. Його license metadata лишається #f до вирішення #367; це технічний build candidate, не public-shippable artifact.

## Розробка

QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 -m wsm_installer --smoke-test
python3 -m unittest tests.test_installer_preview tests.test_installer_gui_contract -v

Для exact Guix stack use python-pyside-6, qtdeclarative, kirigami з channels.lock.scm; не змішуйте Qt 5 Quick Controls із Qt 6.
