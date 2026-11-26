# План: перевірювана virtualization provenance для performance baseline

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Дата: 2026-11-26
- Канонічна задача: [#151 — вимірюваний baseline продуктивності](https://github.com/juv4uk/wsm-desktop/issues/151)
- Базовий `main`: `e53abd2b135b9f8efab1572daeee654d01bb895e`

## Мета

Не дозволяти операторському значенню `--mode` видавати QEMU/VM вимірювання за фізичний baseline. Повторно використовувати read-only `wsm_hwcheck.collector.collect_report()`, а не створювати другий detector.

## Кроки

1. Додати до performance environment поля `detected_virtualization`, `mode_evidence` та джерело detector-а. Відсутні або невизначені дані залишаються `unknown`; відсутність позитивного hypervisor evidence не доводить bare metal.
2. Визначити `physical` як `mismatch` за будь-якого позитивного virtualization evidence. Для запиту `qemu` приймати лише виявлені `qemu` або `kvm`; VMware, Hyper-V, Xen та інші віртуальні платформи — `mismatch`.
3. Зберігати різницю між виявленим `qemu` та `kvm`, щоб не змішувати їх у порівняннях; не виводити TCG/KVM acceleration там, де collector цього не доводить.
4. Додати поведінкові fixture-тести до існуючого collector і performance harness. Не запускати справжні workload-и у звичайних unit-тестах.
5. Оновити українську документацію, CLI help та критерії інтерпретації baseline.
6. Перевірити exact-head CI; зливати тільки після завершення всіх required checks на останньому SHA. Жодних змін BIOS, governor, power limit або фізичних дисків.

## Перевірки

- `python3 -m unittest tests.test_perf_baseline`
- `python3 -m unittest tests.test_hwcheck`
- `make check`
- GitHub required checks на точному HEAD PR.

Локальний запуск команд у цьому середовищі може бути недоступним через мережеве обмеження; у такому разі це явно відокремлюється від CI evidence.
