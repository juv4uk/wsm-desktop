# Розділення привілеїв

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **прототип read-only; root APPLY вимкнено**
- Код: wsm_install/agent.py
- Тести: tests/test_agent.py

## Що вже зроблено

Непривілейована частина може сформувати JSON-план, а окремий root-agent
перевіряє його структуру й команди проти allowlist. Це корисний архітектурний
напрямок: UI не повинен бути процесом із root-правами.

Проте allowlist сам по собі **не** є доказом безпеки операції з диском. JSON
план наразі не підписаний, не прив'язаний до стійкої block-device identity,
а перевірка рядка шляху не доводить, що той самий фізичний пристрій залишився
на місці до кожної destructive boundary.

## Поточна межа

Root-agent зараз працює лише в режимі валідації/preview. Будь-який виклик без
буквального dry_run=True повертає agent.apply-disabled до будь-якого runner,
subprocess або іншої зовнішньої дії. CLI wsm-install-agent без --dry-run
відмовляється, навіть якщо процес має root.

Allowlist береться зі спільної таблиці TRUSTED_TOOLS в install_steps.py, щоб
не мати двох незалежних списків executable paths. Сам факт абсолютного шляху
не доводить, що програма присутня в pinned Guix system closure; це окрема
умова майбутнього APPLY.

## Умови для майбутнього виконання

1. Immutable typed plan із digest, схемою та параметрами layout.
2. Стійка перевірка block-device identity, major/minor, capacity, serial/WWN,
   partition-table digest та topology до початку й перед кожною destructive boundary.
3. Згода, прив'язана до digest плану та ідентичності цілі.
4. Закрита Guix tool closure з перевіреними executable artifacts.
5. Реальні postconditions після кожної команди; exit code не є доказом результату.
6. Відновлення після переривання з повторним читанням фактичного стану.
7. Destructive acceptance на одноразових QEMU block devices та підтвердження,
   що жоден сусідній диск не змінюється.

До виконання цих умов agent не форматує, не монтує й не пише на диск.
