# Класифікація апаратних доказів

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **read-only evidence summary доступний через CLI; не перевірено на фізичному залізі**
- Код: [`wsm_install/classification.py`](../wsm_install/classification.py)
- Тести: [`tests/test_classification.py`](../tests/test_classification.py)
- Канонічна політика: [HARDWARE-COMPATIBILITY-VERDICTS.md](HARDWARE-COMPATIBILITY-VERDICTS.md), власник #22
- Сценарна політика: [INSTALL-CAPABILITY-MATRIX.md](INSTALL-CAPABILITY-MATRIX.md), власник #24
- Реалізаційне виправлення: [#447](https://github.com/juv4uk/wsm-desktop/issues/447)

## Призначення

WSM встановлюється на обладнання, яке наперед невідоме. Класифікатор стисло
показує, які факти є у звіті, але **не** вирішує, чи можна продовжувати
конкретний сценарій інсталяції. Рішення потребує сценарію, рівня впливу,
достатності доказів та підтвердженого fallback — це визначено окремо у
сценарній матриці.

## Три рівні — похідний підсумок, не друга політика

| Канонічний стан | Рівень | Межа твердження |
| --- | --- | --- |
| `supported-tested` | `certified` | Лише конкретна функція з відповідним валідованим профільним evidence |
| `driver-bound-not-tested` | `known` | Драйвер прив'язаний у момент спостереження; функція ще не перевірена |
| `candidate-only` | `known` | Є явний candidate driver, але binding не доведено |
| `known-problem`, `not-detected`, `not-tested`, `unknown`, `not-collected` | `unknown` | Доказів недостатньо або є конкретна проблема |

### Обмеження поточної реалізації

Поточний hardware report v1.0.0 не містить повного coverage manifest за
підсистемами. Тому відсутність device record означає лише
`observation=no-device-record` та `coverage=unknown`; вона не доводить
`not-detected`, `not-collected` або несумісність.

Поле `driver.status` є авторитетним фактом binding. Лише
`status=bound` разом із непорожнім `bound_driver` дає
`driver-bound-not-tested`. Для built-in kernel driver відсутність `module`
нормальна. Наявність `module` або `module_loaded=true` без binding не є
доказом прив'язки. `available-only` разом з явним `candidate` означає
`candidate-only`; `not-applicable` не є помилкою драйвера.

Firmware не є окремою категорією пристрою: у hardware report це вкладений
per-device факт. Класифікатор не підставляє стан драйвера материнської плати
замість firmware verdict. У `device_evidence` зберігаються
`requirement`, `runtime_status`, спостережені файли, package candidates,
kernel-log evidence та redistribution status; планувальник окремо обробляє
обов'язковий runtime firmware. Самі `missing` або `load-error` не
перетворюються тут на глобальний install stop.

Результат функціонального тесту зберігається окремо за парою
`device_id + capability`. `passed` для `display-mode` не доводить GPU
rendering, suspend/resume чи працездатність другого GPU. Провал одного тесту
також не перетворюється на глобальне твердження про всі можливості пристрою.

`wsm-profile-evidence/2` описує перевірені функції профілю, але не має
device-scoped binding для кожної функції. Через це класифікатор наразі не
приймає довільний evidence dictionary і не присвоює `certified` підсистемі.
Для такого переходу потрібні спільна перевірка bundle через
`wsm_install.profile.problems(..., artifact_root=...)`, точне зв'язування
source report за ID/schema/SHA-256 та доказ scope конкретного пристрою і
capability. Нові поля producer-owned schema не додаються в цьому модулі.

## Межі та install policy

Класифікатор повертає діагностичне зведення. Він не повертає
`stop/warn/proceed` і не містить глобальних списків `CRITICAL` або
`DEGRADING`. Наприклад, Wi-Fi може бути необов'язковим для offline install,
але мережевий connectivity test може бути критичним для network-assisted
сценарію. Такий висновок має робитися лише за явним scenario/policy input,
відповідно до [матриці сценаріїв](INSTALL-CAPABILITY-MATRIX.md).

Діагностичне зведення доступне через CLI після звичайної read-only
валідації звіту:

```sh
python3 -m wsm_install --preflight --dry-run --report hw.json --backend guix --classify
```

Команда повертає `wsm-hardware-classification/2` з трьома рівнями, переліком
спостережених пристроїв, окремими результатами функціональних тестів і
позначенням невідомого coverage. Вона **не** повертає `stop/warn/proceed`,
не приймає profile evidence і не дозволяє підтвердити план.

Шлях `--install` не використовує цей трирівневий підсумок як глобальний
gate. Він повторно використовує `build_plan()` для перевірки явно заявлених
критичних ролей і обов'язкового runtime firmware у звіті; відсутні ролі
залишаються попередженнями, а не доказом відсутності пристрою. Це поки що
консервативний report-level dry-run, а не повна сценарна реалізація матриці
[#24](https://github.com/juv4uk/wsm-desktop/issues/24). `--accept-degraded`
не перекриває блокувальні помилки планувальника; цей прапорець прибрано разом
із глобальною класифікацією `stop/warn/proceed`.

Класифікатор не читає sysfs, не запускає драйвери, не змінює firmware, не
виконує мережеві запити, не вибирає диск і не дозволяє backend mutation.

## Непокрита capability: suspend/resume

Серед підсистем немає `suspend`, хоча «працює, але не засинає» — один із найчастіших дефектів
на сучасних ноутбуках. Причина не в байдужості: у звіті `wsm-hwcheck` немає
категорії, з якої це можна взяти, а додавання категорії — зміна схеми
[HARDWARE-REPORT](../schemas/hardware-report.schema.json) і належить власникам
[#5](https://github.com/juv4uk/wsm-desktop/issues/5)/[#24](https://github.com/juv4uk/wsm-desktop/issues/24).

Що саме треба буде збирати, вже відомо з документації ядра й досвіду дистрибутивів:

- `/sys/power/mem_sleep` — перелік доступних варіантів suspend і варіант,
  **поточний для наступної спроби** запису `mem` у `/sys/power/state`.
  Квадратні дужки позначають обраний зараз режим, а не «режим за замовчуванням»:
  `s2idle [deep]` означає, що доступні обидва режими й наразі обрано `deep`;
  `[s2idle] deep` — що доступні обидва, але обрано `s2idle`; `[s2idle]`
  означає, що в цьому виводі доступний лише `s2idle`. На AMD `deep` відповідає
  S3, якщо платформа його надає;
- `/sys/power/suspend_stats/last_hw_sleep` — тривалість часу в апаратному
  sleep state під час останнього циклу suspend/resume, у мікросекундах.
  Якщо значення перевищує `max_hw_sleep`, апаратна статистика може бути
  неточною; сам лічильник не підтверджує успішність усіх етапів resume;
- рядок ядра `Low-power S0 idle used by default for system suspend` —
  повідомлення про вибір s2idle як режиму за замовчуванням для ACPI Low Power
  S0 у відповідному сценарії ініціалізації. Його слід зіставляти з поточним
  значенням `mem_sleep`, а не трактувати як окремий тест працездатності.

Це **не** доказ, що сон працює: режим може бути доступним, а пристрій — не
входити в низьке споживання. Тому майбутня категорія мусить розрізняти
«режим заявлено», «режим обрано» і «цикл сну пройдено з виміряним результатом» —
рівно як з firmware у [REPORT-FORMAT.md](hardware/REPORT-FORMAT.md).
