# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **лише preview; реальний APPLY вимкнено**
- Код: wsm_install/executor.py та wsm_install/cli.py
- Тести: tests/test_executor.py і tests/test_cli_install.py

## Поточна межа

CLI wsm-install --install будує розкладку й показує argv, але не змінює диски.
Параметр --execute тимчасово й безумовно відхиляється з
execute.apply-disabled до запуску будь-якої команди. Executor не містить
runner-а чи verifier-а; він лише формує preview із позначками руйнівних кроків.

Параметр --target-size-bytes є **введеною користувачем оцінкою для побудови
плану**, а не виміряною місткістю пристрою. CLI поки не читає фактичний
block-device capacity, major/minor, serial/WWN, sysfs topology або таблицю
розділів. Значення --acknowledge-disk лише задовольняє консервативну
перевірку планувальника; воно не є дозволом на запис і не прив'язане до
ідентичності пристрою чи digest плану.

Це свідоме fail-closed рішення після аудиту першого executor prototype:
окремий рядок підтвердження диска не доводив, що переданий argv торкався саме
цього диска; target identity та layout digest не перечитувалися перед
destructive boundary; перевірка GPT після sgdisk була відсутня; partprobe і
udevadm повертали безумовний успіх; а blkid викликався через успадкований
PATH. Тому non-dry-run вимкнено, а попередні твердження про захист розміром
диска виправлено.

## Preview

    wsm-install --preflight --dry-run --report hw.json --backend guix \
        --install --target-disk /dev/nvme0n1 --target-size-bytes 274877906944 \
        --acknowledge-disk /dev/nvme0n1

Команда показує план. Вона не доводить, що вказаний шлях існує або що
користувач ввів правильну місткість. Значення розміру є лише параметром моделі.

    wsm-install --preflight --dry-run --report hw.json --backend guix \
        --install --execute --target-disk /dev/nvme0n1 \
        --target-size-bytes 274877906944 --acknowledge-disk /dev/nvme0n1

Другий приклад **відхиляється** з execute.apply-disabled. Навіть правильний
рядок acknowledgement не вмикає APPLY.

## Умови для майбутнього APPLY

Реальний виконавець може бути повернений лише окремим змістовним PR після
виконання всіх пунктів:

1. **Єдиний immutable typed plan.** Executor отримує layout, filesystem,
   target identity та всі параметри з одного snapshot; довільний список
   команд і окремий рядок disk не є допустимим API.
2. **Стійка ідентичність цілі.** До початку й перед кожною destructive
   boundary перечитуються block-device type, major/minor, capacity, logical
   sector size, stable identity за наявності, partition-table digest,
   partition number/start/end/type та topology. Зміна значення анулює згоду.
3. **Згода прив'язана до digest.** Підтвердження містить target identity і
   digest повного плану; воно перевіряється перед кожним записом.
4. **Закритий набір інструментів.** Кожний executable має абсолютний шлях із
   перевіреної Guix package closure. Ніяких bare PATH lookup чи shell strings.
5. **Справжні postconditions.** Після GPT write таблиця перечитується й
   звіряється з layout; після rescan перевіряються device nodes та major/minor;
   після mkfs — filesystem UUID/type/label; після mount — точний source/target
   у mountinfo. Команда без verifier-а не може завершитися як success.
6. **Переривання та відновлення.** Після помилки фактичний стан перечитується;
   повтор destructive кроку не виконується лише за журналом. Потрібні recovery
   semantics і disposable snapshot/rollback.
7. **Acceptance у disposable QEMU.** Реальні loop-backed/QEMU block devices
   мають довести target identity, точні postconditions, відмову при підміні,
   interruption і відсутність змін на сусідньому диску. Mock-тести — лише
   доповнення, не доказ безпеки APPLY.

До завершення цих критеріїв підтримуваний шлях закінчується на read-only
preflight, typed plan і preview. Не запускайте цей код на фізичному диску.
