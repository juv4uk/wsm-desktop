# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **лише preview; реальний APPLY вимкнено**
- Код: wsm_install/executor.py
- Тести: tests/test_executor.py

## Поточна межа

Функція execute() — історична назва API. У поточній реалізації вона лише
показує план дій як argv і позначає руйнівні кроки. Будь-який виклик із
dry_run=False завершується execute.apply-disabled до виводу чи виконання
команд. У модулі немає runner-а, verifier-а або шляху, яким можна запустити
sgdisk, mkfs, mount чи guix system init.

Це свідоме fail-closed рішення після перевірки першого executor prototype:
окремий рядок підтвердження диска не доводив, що переданий argv торкався саме
цього диска; target identity та layout digest не перечитувалися перед
destructive boundary; перевірка GPT після sgdisk була відсутня; а blkid
викликався через успадкований PATH. Unit tests зі штучними runner/verifier
не могли довести ці властивості. Тому реальне виконання тимчасово вимкнено,
а не оголошено готовим.

## Умови для майбутнього APPLY

Реальний виконавець може бути повернений лише окремим змістовним PR після
виконання всіх пунктів:

1. **Єдиний immutable typed plan.** Executor сам отримує layout, filesystem,
   target identity та всі параметри зі snapshot; довільний список команд і
   окремий рядок disk не є допустимим API.
2. **Стійка ідентичність цілі.** До початку й перед кожною destructive
   boundary перечитуються block-device type, major/minor, capacity, logical
   sector size, stable device identity за наявності, partition-table digest,
   partition number/start/end/type та фактична топологія. Зміна будь-якого
   значення анулює попередню згоду.
3. **Згода прив'язана до digest.** Одноразове підтвердження містить target
   identity і digest повного плану; воно перевіряється перед кожним записом,
   а не лише під час старту.
4. **Закритий набір інструментів.** Кожний executable має абсолютний шлях із
   перевіреної Guix package closure. Ніяких bare blkid, PATH lookup або
   shell command strings. Наявність шляху в коді не доводить наявність пакета
   у live ISO.
5. **Справжні postconditions.** Після GPT write повторно читається таблиця й
   звіряється з погодженим layout; після rescan перевіряються device nodes та
   їхня major/minor; після mkfs перевіряється filesystem UUID/type/label;
   після mount звіряється точний source/target у mountinfo. Команда без
   визначеного verifier-а не може завершитися як success.
6. **Переривання та відновлення.** Після помилки потік зупиняється, фактичний
   стан перечитується, а destructive крок не повторюється лише за журналом.
   Потрібні recovery semantics та snapshot/rollback стратегія для disposable
   середовища.
7. **Acceptance у disposable QEMU.** Тести мають працювати з реальними
   loop-backed/QEMU block devices і довести правильний target, точні
   postconditions, відмову при підміні пристрою, interruption та відсутність
   змін на сусідньому диску. Unit-тести з mock-ами залишаються доповненням,
   а не доказом APPLY safety.

До завершення цих критеріїв підтримуваний шлях закінчується на read-only
preflight, typed plan і preview. Не запускайте цей код на фізичному диску.
