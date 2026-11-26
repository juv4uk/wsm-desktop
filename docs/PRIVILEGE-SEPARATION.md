# Розділення привілеїв

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; жоден installer frontend не виконує дискові команди**
- Код: `wsm_install/executor.py`, `wsm_install/cli.py`, `wsm_install/guided.py`, `wsm_install/tui.py`, `wsm_install/agent.py` та Calamares module
- Тести: `tests/test_executor.py`, `tests/test_cli_install.py`, `tests/test_guided.py`, `tests/test_tui.py`, `tests/test_agent.py`, `tests/test_calamares_module.py`

## Політика

CLI, Guided, TUI, Calamares і privileged agent працюють у режимі preview-only.
Будь-який запит APPLY відхиляється до виклику зовнішнього виконавця:

- `wsm-install --execute` відхиляється ще до обробки звіту та вибору frontend;
- Guided і TUI показують план, але не викликають install callback;
- Calamares вимагає буквальне `wsmDryRun=True`, а preview повертає non-success результат, щоб його не можна було сплутати з встановленням;
- privileged agent вимагає `--dry-run`; без цього повертає `agent.apply-disabled`;
- executor має preview-only API: `dry_run` повинен бути саме `True`, інакше повертається `execute.apply-disabled`.

## Перевірки плану

Executor перевіряє:

1. whole-device target за allow-listed формою `/dev/...`;
2. що кожне явне посилання `/dev/...` в argv, включно з аргументами на кшталт `--device=/dev/sda1`, належить саме target-диску або його partition;
3. типи кроків, непорожній argv, контрольні символи, purpose та destructive flag.

Partition naming розрізняється для SATA/SCSI (`/dev/sda1`) та NVMe/MMC (`/dev/nvme0n1p1`). Невідповідність завершується `execute.device-mismatch`; preview іншого диска не формується.

Allowlist у privileged agent є лише обмеженням для плану, який показують. Вона **не дозволяє виконувати** `partprobe`, `mkfs`, `mount` чи інші команди.

## Recovery

`wsm-install-agent --recover --plan PATH` читає журнал і формує звіт; не змінює диски. `--recover` без `--plan` завершується контрольованим exit code 2. Це важливо: відсутнє джерело recovery даних не повинно породжувати traceback або фальшивий звіт.

## Умови повернення APPLY

Реальний APPLY може повернутися лише окремим reviewed change, який доводить:

- стабільну identity block device і повторну перевірку перед кожною destructive boundary;
- незмінний typed plan із digest-bound consent;
- звірку кожного target path з immutable plan;
- обмежений та перевірений набір виконуваних інструментів;
- перевірювані postconditions і контрольоване відновлення після переривання;
- destructive acceptance у disposable QEMU-дисках, включно з перериванням на кожній destructive boundary.

Цей PR не виконує жодних операцій форматування, монтування, bootloader install або запису на реальні диски.
