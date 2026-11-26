# Виконавець кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальний APPLY вимкнено**
- Код: `wsm_install/executor.py`
- Тести: `tests/test_executor.py`, `tests/test_cli_install.py`, `tests/test_guided.py`, `tests/test_calamares_module.py`

## Чому виконання зараз вимкнене

Попередній executor приймав довільний список `Step.command`, окремий рядок acknowledgement і запускав команди через subprocess. Рядковий збіг `--target-disk == --acknowledge-disk` не доводить, що block device лишився тим самим між плануванням і виконанням. Так само успішний exit code не доводить, що postcondition справді настав.

Тому поточний executor:
- валідовує форму preview-кроків;
- повертає кожен argv з позначенням `skipped`;
- явно повідомляє, що команда не виконувалася;
- відмовляє на `dry_run=False` з `execute.apply-disabled`;
- не має subprocess runner, verifier injection або journal side effect для реального виконання.

Це тимчасова безпечна межа, а не готовий інсталятор.

## Всі frontend-и мають однакову межу

CLI `--execute` відхиляється до читання report і disk discovery. Guided flow і TUI можуть тільки сформувати preview. TUI не приймає install callback і не показує «Installation finished». Calamares повертає failure tuple для preview, оскільки `None` означає успішне завершення jobmodule.

Privileged `wsm-install-agent` також відмовляє на `dry_run=False`, зокрема коли викликається від root. Жоден frontend не може обійти спільну межу.

## Що потрібно для майбутнього APPLY

Перед окремим рішенням про відновлення APPLY мають бути реалізовані та протестовані:
1. Immutable typed plan із digest усіх параметрів, filesystem labels, firmware/layout і exact Guix configuration.
2. Фактична block-device identity (major/minor, stable sysfs identity, size/geometry/topology) і повторна перевірка перед кожною destructive операцією.
3. ACK, прив'язаний до plan digest + target identity, а не рядка шляху.
4. Точний allowlist команд/argv та підтверджений live package closure; абсолютний шлях сам по собі не доводить, що binary присутній.
5. Обов'язкові typed postconditions для GPT, partition nodes, filesystem type+label, mount source identity, Guix generation та boot artifact.
6. Переривання після кожного кроку, recovery journal, target revalidation та disposable qcow2 QEMU acceptance.
7. Installed boot і post-boot health verification до стану COMPLETE.

До проходження цих критеріїв `execute.apply-disabled` не повинен мати feature flag, environment override або Calamares global-storage bypass.

## Журнал recovery

`wsm_install/journal.py` містить JSONL writer/parser та recovery report, але не підключений до активного APPLY. Його unit tests перевіряють формат і стійкість читання; вони не доводять, що будь-який диск уже встановлювався або що журнал атомарно описує реальне виконання. При майбутньому APPLY journal open/write/fsync failure має зупиняти транзакцію до першої destructive команди.
