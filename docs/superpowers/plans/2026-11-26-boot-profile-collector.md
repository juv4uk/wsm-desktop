# План: read-only boot milestones та service critical path

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата: 2026-11-26
- Канонічна задача: [#151 — вимірюваний baseline boot, services і desktop workloads](https://github.com/juv4uk/wsm-desktop/issues/151)
- Базовий `main`: `60e1af8001a36ab25399531aee4e2475c1381ea2`

## Мета

Додати явну ручну команду, яка збирає boot milestones та critical path systemd з поточного boot. Не запускати її в hardware preflight, інсталяторі, фоні або звичайному CI.

## Реалізація

1. Використати штатний read-only `systemd-analyze time`, `blame`, `critical-chain`, а не вигадувати власний timer або реконструювати boot із непрямих timestamps.
2. Зібрати default target і `graphical.target` окремо, зберігати сирий stdout/stderr, exit code, argv, duration, timeout та truncation.
3. Кожна команда — fixed argv allowlist без shell; локаль `C`, stdin закритий, timeout обмежений, output у JSON bounded.
4. Записати boot identity як короткий SHA-256 digest boot ID (без raw UUID), uptime, kernel/machine і virtualization evidence від canonical read-only collector.
5. Відсутня systemd, недоступний manager, timeout, nonzero exit або неповний chain — `unknown/partial`, не нуль і не pass.
6. Документувати обмеження: `time` завершується на spawn services, а не на повній готовності desktop; `blame` не враховує parallelism; critical-chain показує один шлях і має caveats щодо socket activation, device units та jobs/timeouts.
7. Один профіль описує один boot; статистику між boots агрегувати окремо, не називати п'ять повторів усередині одного boot незалежними samples.

## Перевірки

- Unit-тести fixed argv/no shell, missing binary, timeout, nonzero exit, bounded output, boot ID privacy та unavailable procfs.
- Повний `make check` у GitHub Actions на exact PR HEAD.
- Ручне виконання на реальному systemd host не заявляти до запуску команди на цільовій системі.

Без змін unit-файлів, systemd-конфігурації, bootloader, BIOS/UEFI, EFI variables, governor, power controls або дисків.
