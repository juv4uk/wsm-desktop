# План: read-only boot milestones та service critical path

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата: 2026-11-26
- Канонічна задача: [#151 — вимірюваний baseline boot, services і desktop workloads](https://github.com/juv4uk/wsm-desktop/issues/151)
- Базовий `main` на момент повторного review: `2ab21c7c86429cc2a2c1fc98a96f565ac9a7d143`

## Мета

Додати явну ручну команду, яка збирає boot/service-manager evidence з поточного boot для systemd або GNU Shepherd. Не запускати її в hardware preflight, інсталяторі, фоні або звичайному CI.

## Реалізація

1. Визначати manager за `/proc/1/comm`; для systemd використовувати read-only `systemd-analyze time`, `blame`, `critical-chain`, для GNU Shepherd — `herd status`, `herd log`, `herd graph`. Не реконструювати час із непрямих timestamps.
2. Для systemd збирати default target і `graphical.target` окремо; для Shepherd зберігати snapshot статусів, event log та dependency graph. Зберігати сирий stdout/stderr, exit code, argv, duration, timeout та truncation.
3. Кожна команда — fixed argv allowlist без shell; локаль `C`, stdin закритий, timeout обмежений, output у JSON bounded. Для system scope binary lookup використовує лише довірені системні каталоги, а не inherited user `PATH`; user Shepherd лишається в непривілейованому user PATH.
4. Записати boot identity як короткий SHA-256 digest boot ID (без raw UUID), uptime, kernel/machine і virtualization evidence від canonical read-only collector.
5. Невідомий PID 1 не отримує fallback. Недоступний executable/socket, timeout, nonzero exit або неповний chain/log — `unknown/partial`, не нуль і не pass. User Shepherd не видавати за system boot; не виконувати `sudo` автоматично.
6. Документувати обмеження: `time` завершується на spawn services, а не на повній готовності desktop; `blame` не враховує parallelism; critical-chain показує один шлях і має caveats щодо socket activation, device units та jobs/timeouts.
7. Один профіль описує один boot; статистику між boots агрегувати окремо, не називати п'ять повторів усередині одного boot незалежними samples.
8. Чітко відокремити boot observation від shutdown/unmount acceptance: `herd status/log/graph` не доводять завершення stop handlers або unmount цільових файлових систем. Точний Free Guix source commit уже визначає Shepherd 1.0.9 (`docs/UPSTREAMS.md`), але це не доводить, що конкретний образ зібраний із цим package або що саме ця версія працює в runtime; для цього потрібні Guix closure/build та runtime boot evidence.

## Перевірки

- Unit-тести fixed argv/no shell, missing binary, timeout, nonzero exit, bounded output, boot ID privacy та unavailable procfs.
- Повний `make check` у GitHub Actions на exact PR HEAD.
- Ручне виконання на реальному Linux host із systemd або GNU Shepherd не заявляти до запуску команди на цільовій системі.

Без змін unit-файлів, systemd-конфігурації, bootloader, BIOS/UEFI, EFI variables, governor, power controls або дисків.
