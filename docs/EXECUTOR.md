# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальний APPLY вимкнено**
- Код: [`wsm_install/executor.py`](../wsm_install/executor.py), [`wsm_install/cli.py`](../wsm_install/cli.py)
- Frontends: CLI, `--guided`, `--tui`, опційний Calamares
- Тести: `tests/test_executor.py`, `tests/test_cli_install.py`, `tests/test_guided.py`, `tests/test_tui.py`, `tests/test_calamares_module.py`

## Поточна межа

Усі чотири входи використовують один `wsm_install.executor.execute()`. Він приймає лише
preview-запити: будь-який `dry_run`, відмінний від буквального `True`, повертає
`execute.apply-disabled` **до будь-якого виводу або зовнішньої дії**. У ньому немає
runner-а, verifier-а, `subprocess` чи shell-викликів.

CLI додатково відхиляє `--execute` до читання звіту або вибору frontend-а. Тому
`--install --execute` і `--guided --execute` не доходять до планувальника.
Збіг рядків `--target-disk` та `--acknowledge-disk` не є дозволом на запис.

## Чотири входи — одна межа

| Вхід | Дозволена дія | Поведінка APPLY |
| --- | --- | --- |
| `wsm-install --install` | Побудувати й показати argv-план | `--execute` відхиляється |
| `wsm-install --guided` | Вибрати ціль і показати read-only preview | Немає кроку «Install now» чи install callback |
| `wsm-install --tui` | Псевдографічний вибір цілі й read-only preview | Немає екрана «Enter to install» чи install callback |
| Calamares `wsm_deploy` | Передати план спільному executor-у | `wsmDryRun=false` відхиляється executor-ом |

У guided mode повторне введення шляху диска підтверджує лише те, для якого
пристрою показати preview. Це не destructive consent. Calamares має той самий
контракт і не може мати власного шляху до `mkfs`, `mount` або `guix system init`.

## Що доведено, а що ні

- У unit/CLI tests перевіряється, що навіть **правильний** matching
  `--acknowledge-disk` не дозволяє APPLY.
- Guided і TUI tests перевіряють, що flow викликає лише preview callback, не показує
  install confirmation screen і не викликає жодного install callback.
- Calamares test перевіряє, що `wsmDryRun=false` повертає
  `execute.apply-disabled`.
- Це не є доказом безпеки майбутнього APPLY і не є QEMU install acceptance.
  Жоден тест цього PR не запускає `sgdisk`, `mkfs`, `mount` чи `guix system init`.

Параметр `--target-size-bytes` наразі є **введеною користувачем оцінкою для
побудови плану**. CLI не читає фактичну місткість block device, major/minor,
serial/WWN, sysfs topology або таблицю розділів. Старе твердження, що звірка
цієї ж введеної величини захищає від підміни диска, було неправильним і вилучене.

## Умови для майбутнього APPLY

Реальний виконавець може повернутися лише окремим reviewed PR після виконання всіх умов:

1. **Immutable typed plan.** Executor отримує layout, filesystem, target identity
   та всі параметри з одного snapshot; довільний список команд і окремий рядок
   disk не є допустимим API.
2. **Стійка ідентичність цілі.** До початку й перед кожною destructive boundary
   перечитуються block-device type, major/minor, capacity, logical sector size,
   stable identity за наявності, partition-table digest, partition number,
   start/end/type та topology. Зміна значення анулює згоду.
3. **Згода, прив'язана до digest.** Підтвердження містить target identity і digest
   повного плану; воно перевіряється перед кожним записом.
4. **Закрита tool closure.** Кожний executable походить з перевіреної Guix package
   closure. Абсолютний шлях сам по собі не доводить, що програма є в образі.
5. **Справжні postconditions.** Після GPT write таблиця перечитується й
   звіряється з layout; після rescan перевіряються device nodes та major/minor;
   після mkfs — filesystem UUID/type/label; після mount — точний source/target
   у mountinfo. Команда без verifier-а не може завершитися як success.
6. **Переривання та відновлення.** Після помилки фактичний стан перечитується;
   повтор destructive кроку не виконується лише за журналом. Потрібні recovery
   semantics і disposable snapshot/rollback.
7. **Acceptance у disposable QEMU.** Реальні loop-backed/QEMU block devices
   доводять target identity, точні postconditions, відмову при підміні,
   interruption і відсутність змін на сусідньому диску. Mock-тести — лише
   доповнення, не доказ безпеки APPLY.

До завершення цих критеріїв підтримуваний шлях закінчується на read-only
preflight, typed plan і preview. Не запускайте цей код на фізичному диску.
