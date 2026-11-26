# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; APPLY вимкнено в усіх frontend-ах**
- Код: [`wsm_install/executor.py`](../wsm_install/executor.py), [`wsm_install/agent.py`](../wsm_install/agent.py)
- Frontends: CLI, guided, TUI, Calamares
- Тести: `tests/test_executor.py`, `tests/test_agent.py`, `tests/test_cli_install.py`, `tests/test_guided.py`, `tests/test_tui.py`, `tests/test_calamares_module.py`

## Єдина межа

Спільний `wsm_install.executor.execute()` приймає лише preview-запити:
будь-яке значення `dry_run`, крім буквального `True`, повертає
`execute.apply-disabled` до виводу або зовнішньої дії. У модулі немає
`subprocess`, runner-а або verifier-а.

Привілейований `wsm-install-agent` також відмовляє на `dry_run=False`
з `agent.apply-disabled`. Allowlist тут використовується для перевірки
структури плану, а не як дозвіл на виконання.

## Статус preview-кроку

Кожен запланований крок повертається зі статусом `not-run` і деталлю
`command not executed`. Це означає, що executor перевірив і показав намір,
але не запускав команду. `not-run` не є `passed`, `skipped` або доказом
працездатності диска чи успішного виконання операції. Такий стан зберігає
спільний контракт спостереження WSM: відсутність виконання не можна
перетворювати на позитивний вердикт.

## Поведінка frontend-ів

| Вхід | Дозволено | Заборонено |
| --- | --- | --- |
| CLI `--install` | побудувати й показати план | `--execute`, навіть із правильним шляхом підтвердження |
| CLI `--guided` | вибрати ціль і показати preview | install callback і destructive confirmation |
| CLI `--tui` | навігація, вибір і preview | install callback та екран «Installing» |
| Calamares `wsm_deploy` | внутрішній read-only preview | `None` success для неінстальованої системи; missing/false `wsmDryRun` також відхиляється |

Guided/TUI можуть завершити побудову preview з кодом 0, але явно повідомляють,
що APPLY вимкнено й WSM **не встановлено**. Calamares required jobmodule завжди
повертає failure tuple, бо успішне завершення цього job означало б, що система
встановлена.

## Що доведено

- Спільний executor відхиляє `dry_run=False` до будь-якого output.
- Його API не приймає runner, verifier або окремий acknowledgement рядок.
- Root-агент не має runner/verifier API та не виконує план навіть із root.
- CLI відхиляє `--execute` до report loading і вибору frontend-а.
- Guided/TUI приймають лише preview callback.
- Calamares не повертає `None` для preview, відсутнього або false `wsmDryRun`.
- Жоден тест цього набору не запускає `sgdisk`, `mkfs`, `mount` чи Guix deploy.

## Умови для майбутнього APPLY

Реальний виконавець може повернутися лише окремим reviewed PR після виконання
всіх умов:

1. Immutable typed plan із target identity, filesystem, layout, mount facts
   та digest одного snapshot.
2. Повторна перевірка block-device type, major/minor, stable identity,
   capacity, sector size, partition table і topology перед кожною destructive
   boundary.
3. Digest-bound consent, яке перевіряється перед кожним записом; повторне
   введення `/dev/...` саме по собі не є дозволом.
4. Закрита й перевірена Guix package closure для кожного executable.
5. Postconditions після GPT write, partprobe/udev, mkfs і mount: реальні
   partition nodes, type/offset/size, filesystem UUID/type та mountinfo.
6. Recovery journal із перевіркою фактичного стану після переривання; журнал
   не є дозволом повторювати destructive дію.
7. Disposable-QEMU acceptance з підміною target, interruption і доказом,
   що сусідній диск не змінюється.

До виконання цих умов підтримуваний шлях закінчується на preflight, typed plan
і preview. Не запускайте код на фізичному диску.
