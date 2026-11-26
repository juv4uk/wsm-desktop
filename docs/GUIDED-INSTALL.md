# Покроковий вибір цілі та preview у консолі

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальне встановлення вимкнено**
- Код: [`wsm_install/guided.py`](../wsm_install/guided.py)
- Тести: `tests/test_guided.py`

## Запуск

```sh
wsm-install --preflight --dry-run --report hw.json --backend guix --guided
```

Guided flow показує диски, дає вибрати один, firmware та попросить повторно ввести його шлях. Це відповідає на запитання «для якого диска побудувати preview?». Це **не** destructive consent та не доказ реальної ідентичності пристрою.

Після вибору WSM будує read-only preview. Екран прямо повідомляє:

- APPLY вимкнено;
- команди форматування/монтування не запускалися;
- жодних змін не внесено.

У поточному API немає install callback і немає запитання «Install now?».

## Межі доказів

Список дисків читається із sysfs. Розмір у ньому — спостереження для відображення і планування, але він не є target identity snapshot. CLI не перевіряє самостійно major/minor, WWN/serial, topology або partition-table digest перед кожною операцією, тому preview не можна використовувати як згоду на запис.

Реальне APPLY може бути окремо спроєктоване лише після target-bound immutable plan, повторної identity revalidation, digest-bound consent, trusted Guix tool closure, postconditions, recovery semantics та disposable-QEMU acceptance. Див. [EXECUTOR.md](EXECUTOR.md).
