# Класифікація заліза: три рівні впевненості

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **read-only бібліотечний прототип**; CLI не інтегровано, на реальному залізі не застосовувалось
- Код: [`wsm_install/classification.py`](../wsm_install/classification.py)
- Тести: `tests/test_classification.py` (24)
- Словник: [OBSERVATION-PRINCIPLES.md](OBSERVATION-PRINCIPLES.md)
- Канонічні стани та рішення: [HARDWARE-COMPATIBILITY-VERDICTS.md](HARDWARE-COMPATIBILITY-VERDICTS.md)
- Сценарні вимоги й fallback: [INSTALL-CAPABILITY-MATRIX.md](INSTALL-CAPABILITY-MATRIX.md)

## Призначення

WSM ставлять на обладнання, яке заздалегідь невідоме. Класифікатор стисло
підсумовує докази для виявлених підсистем, але не перетворює інвентаризацію на
обіцянку сумісності й не приймає інсталяційних рішень.

## Три рівні — це похідний підсумок

Внутрішнім джерелом істини залишаються сім канонічних станів доказів із
[HARDWARE-COMPATIBILITY-VERDICTS.md, §2](HARDWARE-COMPATIBILITY-VERDICTS.md):

| Канонічний стан | Рівень |
| --- | --- |
| `supported-tested` | `certified` |
| `driver-bound-not-tested` | `known` |
| `candidate-only`, `known-problem`, `not-detected`, `not-tested`, `unknown`, `not-collected` | `unknown` |

### Коли пристрій може бути `known`

Класифікатор читає саме контракт hardware report v1.0.0:

- потрібні одночасно `driver.status == "bound"` і непорожній `driver.bound_driver`;
- built-in драйвер може бути bound без `driver.module`, тому відсутність module link
  не спростовує binding;
- `module-loaded-unbound`, `available-only`, `candidate`, `module_loaded=true`
  або сам `module` не доводять binding;
- `driver.status == "not-applicable"` не є доказом драйверної підтримки.

Окремий успішний функціональний тест зберігається як доказ конкретної capability,
але не сертифікує автоматично всю підсистему.

### Коли пристрій може бути `certified`

`certified` вимагає `ValidatedProfileEvidence`, яке створюється тільки через
`load_validated_profile_evidence()` після:

1. перевірки JSON Schema `wsm-profile-evidence/2`;
2. перевірки `profile.scm` та всіх artifact bytes за SHA-256;
3. перевірки безпечних шляхів, functional-test references і profile slug;
4. збігу `report_id` і `report_schema_version`;
5. збігу SHA-256 **точних raw bytes** джерельного hardware report;
6. успішного зіставлення `hardware_signature` із PCI vendor/device IDs цього звіту
   через спільний [profile matcher](../wsm_install/profile_match.py). Профіль без
   signature або з невідповідною signature не може бути сертифікований.

Звичайний словник Python із `{"status": "pass"}` не приймається. Bundle v2 називає
функцію підсистеми, але не має per-device ID. Тому один `storage: pass` не може
сертифікувати кілька storage device records: для такого випадку потрібен
окремий per-device evidence contract із власниками #5/#171. Matcher читає
реальний report v1.0.0, де PCI vendor і device IDs зберігаються окремими полями.

## Coverage — окремо від рівня

Report schema v1.0.0 не містить повного per-subsystem coverage manifest.
Тому відсутність device record означає:

- `level=unknown`;
- `coverage=unknown`;
- `assessed=false` — немає запису цієї підсистеми, який можна класифікувати.

Це **не** доводить, що collector повністю пройшов цю підсистему й не знайшов
пристрою. Не можна виводити `not-detected`, `not-collected`, несумісність або
готовність до встановлення з відсутності record.

Коли записи є, `coverage=reported-device-records` означає лише, що оцінено
наявні записи. Це не обіцянка повного покриття фізичної системи.

## Класифікатор не вирішує, чи можна встановлювати

`classification.py` повертає `decision=not-evaluated`. Він не містить статичних
списків `CRITICAL`/`DEGRADING` і не згортає невідоме сховище, GPU чи Wi-Fi у
глобальний `stop` або `warn`.

Інсталяційне рішення належить сценарній політиці: обраний сценарій, рівень
впливу функції та підтверджений fallback визначають `hard-stop`, `soft-stop`,
`warn-and-continue` або `continue`. Джерело — [HARDWARE-COMPATIBILITY-VERDICTS.md,
§3–4](HARDWARE-COMPATIBILITY-VERDICTS.md) разом із
[INSTALL-CAPABILITY-MATRIX.md](INSTALL-CAPABILITY-MATRIX.md).

## Межі інтеграції

Модуль є read-only бібліотечним прототипом. `wsm-install --classify` не існує й
не згадується як доступна команда. CLI preflight та Guix handoff продовжують
користуватися власними versioned contracts; цей класифікатор не запускає
команди, не завантажує модулі, не змінює firmware, диски, bootloader чи мережу.

Приклад використання бібліотеки після schema validation звіту:

\`\`\`python
from wsm_install.classification import classify, explain

result = classify(report)
print(explain(result))
# decision=not-evaluated: install readiness belongs to the scenario policy.
\`\`\`

Невідоме не означає несправне. Але й відсутність доказу не означає, що функція
працює.
