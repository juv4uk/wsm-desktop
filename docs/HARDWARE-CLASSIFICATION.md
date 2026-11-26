# Класифікація апаратних доказів

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **обмежене read-only зведення; не підключено до CLI та не перевірено на фізичному залізі**
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

Це library-only компонент: прикладу `wsm-install --classify` немає, бо
відповідного CLI шляху ще не реалізовано. Він не читає sysfs, не запускає
драйвери, не змінює firmware, не виконує мережеві запити, не вибирає диск і
не дозволяє backend mutation.

## Непокрита capability: suspend/resume

У звіті `wsm-hwcheck` наразі немає категорії suspend. Майбутній collector
має розрізняти щонайменше:
- `/sys/power/mem_sleep` — доступні режими й поточний default;
- `/sys/power/suspend_stats/last_hw_sleep` — виміряний час у hardware sleep
  після останнього циклу suspend/resume;
- повідомлення ядра про low-power S0 idle — використаний шлях s2idle.

Жодне з цих спостережень окремо не доводить успішний end-to-end цикл сну та
пробудження. Читання має бути read-only: `mem_sleep` є керованим sysfs
атрибутом, його не можна записувати з inventory collector.
