# Розділення привілеїв

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **архітектурний прототип; root-agent зараз preview-only**
- Код: [`wsm_install/agent.py`](../wsm_install/agent.py), [`wsm_install/executor.py`](../wsm_install/executor.py)
- Тести: `tests/test_agent.py`

## Модель загроз

UI та файл-план походять із непривілейованого контексту. Вони є недовіреним джерелом даних. Root-agent не повинен сприймати JSON-план, повторно введений шлях диска або allowlisted executable як дозвіл змінювати block device.

Розділення UI і привілейованого worker-а зменшує площу атаки, але саме по собі не робить операцію безпечною. Agent не є sandbox і не доводить фізичну ідентичність пристрою.

## Поточна поведінка

Непривілейована сторона може згенерувати JSON preview plan через `--write-plan`. `wsm-install-agent --plan PATH` читає bounded regular file, відхиляє symlink/special file та перевіряє:

- schema і кількість кроків;
- повний абсолютний executable allowlist;
- типи argv, відсутність control characters і shell metacharacters;
- whole-device path;
- відповідність кожного явного `/dev/...` operand оголошеному диску.

Після цього agent передає дані до спільного preview renderer. Він не запускає зовнішні команди. `--execute` не є підтримуваним аргументом; будь-який прямий API-виклик із `dry_run=False` відхиляється до executor-а.

**Allowlist — це лише обмеження структури preview.** Вона не підтверджує, що виконуваний файл існує у Guix live image, що він не підмінений, або що цільовий пристрій є тим самим диском, який було обрано в UI.

## Урок Omarchy #8172

Omarchy виправив привілейований helper, який через bare command lookup міг отримати користувацький `PATH` із пріоритетом на writable checkout. Root-команди мають використовувати довірений, фіксований executable path і контрольоване середовище. WSM додатково не повинен запускати жодну root-команду, доки команда не прив'язана до незалежно перевіреної target identity й погодженого plan digest.

Це причина, чому відокремлення root-agent у WSM не означає автоматичного ввімкнення APPLY.

## Умови для реального writer-а

- root-owned program і контрольовані permissions на worker та всі батьківські каталоги;
- pinned clean environment без успадкованого user PATH та змінних, що можуть підмінити поведінку;
- відкриття plan-файла без symlink/TOCTOU, перевірка ownership, mode, inode/device та digest;
- immutable typed plan з незалежним block-device identity snapshot;
- повторна перевірка major/minor, capacity, partition map і stable identity перед кожним записом;
- digest-bound per-step consent;
- absolute executables із перевіреної locked Guix closure;
- перевірені postconditions, interruption recovery та disposable-QEMU destructive acceptance.

Поки це не виконано, root-agent тільки перевіряє та показує preview. Наявність root не знімає ці обмеження.
