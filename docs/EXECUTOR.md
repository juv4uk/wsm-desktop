# Виконання кроків

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **лише dry-run; APPLY вимкнено fail-closed**
- Код: [`wsm_install/executor.py`](../wsm_install/executor.py)
- Тести: `tests/test_executor.py`

## Чому APPLY поки вимкнено

PR #279 додав executor API, але review після merge виявив, що його первісна
реалізація не доводила безпечність реального запуску:

- точний disk path підтверджувався лише один раз, а не перед кожною destructive дією;
- не було повторної перевірки block-device major/minor, розміру та partition topology;
- довільний `Step.command` можна було передати без allowlist-перевірки;
- `partprobe` та `udevadm settle` повертали `verified`, не перевіряючи наявність і
  відповідність очікуваних partition nodes;
- для невідомого кроку verifier повертав успіх за замовчуванням.

Тому `execute(..., dry_run=False)` зараз завжди відхиляється з
`execute.not-enabled` після перевірки точного acknowledgement і наявності
destructive step. Runner і verifier не викликаються. Це навмисна межа безпеки,
а не тимчасове попередження, яке можна обійти прапорцем.

## Що працює зараз

`execute(..., dry_run=True)` формує звіт про заплановані кроки й не викликає
жодної команди. Тести перевіряють, що навіть підставлені runner/verifier не
викликаються. Невідомий крок у `default_verifier` тепер дає `False`, а не
неявний успіх.

## Умови для майбутнього APPLY

Реальне виконання не можна вмикати, доки немає всіх наступних доказів:

1. **Типізований план замість довільного списку команд.** Executor має сам
   відновлювати або перевіряти canonical argv з `Layout`, filesystem choice
   та fixed target; shell і довільні program paths заборонені.
2. **Жива ідентичність диска.** Перед кожною destructive дією повторно читати
   block-device major/minor, canonical sysfs identity, розмір та topology;
   порівнювати їх із тим, що користувач бачив і підтвердив під час preflight.
3. **Окреме підтвердження кожної destructive дії.** Callback має називати
   точний disk path і конкретну дію; попередня згода не переноситься на
   наступний `sgdisk`/`mkfs`.
4. **Повна GPT-перевірка.** Після `sgdisk` перевірити partition table,
   номер/type/size/offset кожного partition і відповідність очікуваному plan;
   `partprobe`/udev успішні лише після появи правильних block nodes.
5. **Перевірка форматування та mount.** `blkid` має підтвердити саме очікуваний
   filesystem type; mountinfo має підтвердити source major/minor та точну
   target path усередині `/mnt` без symlink/path traversal.
6. **Відновлення та аудит.** Перед першим записом зберегти журнал фаз і
   чітко визначити, що робити після переривання; секрети й зайві hardware IDs
   не потрапляють у логи.

## Заборонені висновки

- Dry-run не доводить, що будь-який пристрій або файлову систему було змінено.
- QEMU guest smoke не є фізичним H170 compatibility test.
- Наявність executor API не означає, що installer frontend обрано чи
  що APPLY реалізований.
- Немає дозволу запускати цей API на фізичному диску; реальне виконання
  програмно заблоковано.

До завершення всіх перелічених умов executor залишається інструментом
побудови dry-run звіту, не механізмом інсталяції.