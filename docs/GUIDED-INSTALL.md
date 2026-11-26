# Покроковий preview в консолі

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **read-only preview; APPLY вимкнено**
- Код: [`wsm_install/guided.py`](../wsm_install/guided.py)
- Тести: `tests/test_guided.py`

## Що робить потік

Консольний інтерфейс показує доступні цілі, дозволяє вибрати диск і firmware
та підтвердити шлях **лише для побудови preview**. Після цього показує план і
завершується повідомленням, що WSM не встановлено.

```sh
wsm-install --preflight --dry-run --report hw.json --backend guix --guided
```

Підтверджений шлях не є дозволом на запис і не може ввімкнути APPLY. У потоці
немає install callback, запуску `mkfs`, `mount` або Guix deployment.

## Збережені принципи

- Диск обирає людина; автоматичного вибору немає.
- Enter або неправильна відповідь зупиняє потік.
- Ввід/вивід ін'єктовані для тестування без термінала чи диска.
- Hardware note є посиланням на спостереження, а не вердиктом сумісності.

## Межі

Preview не доводить доступність інструментів у live image, сумісність обладнання,
реальне розбиття чи встановлення. APPLY може повернутися лише після окремого
reviewed design з target-bound typed plan, digest-bound consent, повторною
перевіркою block-device identity, postconditions і destructive QEMU acceptance.
