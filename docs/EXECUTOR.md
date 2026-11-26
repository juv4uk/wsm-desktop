# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **preview-only; реальний APPLY вимкнено в усіх входах**
- Спільний код: `wsm_install/executor.py`
- Входи: CLI, `--guided`, `--tui`, Calamares jobmodule, `wsm-install-agent`
- Тести: `tests/test_executor.py`, `tests/test_cli_install.py`, `tests/test_guided.py`, `tests/test_tui.py`, `tests/test_calamares_module.py`, `tests/test_agent.py`

## Поточний контракт

`execute()` — це рендерер preview, а не виконавець команд. Він:

- приймає лише буквальне `dry_run=True`;
- відхиляє інше значення до будь-якого виводу чи зовнішньої дії;
- перевіряє типи кроків, форму argv, control characters та узгодженість явних `/dev/...` операндів із названим у preview цілим диском;
- повертає кожен крок зі статусом `skipped`, не запускаючи `sgdisk`, `partprobe`, `mkfs`, `mount` або `guix system init`.

Зіставлення argv із назвою диска — лише перевірка узгодженості preview. Воно **не** читає block-device identity і не доводить, що реальний пристрій має відповідний major/minor, розмір, серійний номер чи partition topology.

## Усі входи мають однакову межу

| Вхід | Дозволено зараз | APPLY |
| --- | --- | --- |
| `wsm-install --install` | Побудувати plan і показати preview | `--execute` відхиляється |
| `wsm-install --guided` | Вибрати ціль та побачити preview | Немає install callback або кроку «Install now» |
| `wsm-install --tui` | Клавіатурна навігація та preview | Немає install callback |
| Calamares `wsm_deploy` | Перевірити дані й показати preview | Job повертає явне повідомлення, що систему НЕ встановлено |
| `wsm-install-agent` | Перевірити обмежений план і показати preview | Реальний запуск не підтримується навіть від root |

Calamares повертає `None` лише для успішного завершення job. Оскільки preview не встановлює систему, job повертає failure/status tuple з прямим повідомленням. Так UI не може показати «успішне встановлення» після read-only preview.

`--target-size-bytes` — введена користувачем оцінка для побудови плану. Вона не є результатом незалежного sysfs probe й не захищає від підміни диска. Повторне введення шляху диска підтверджує лише вибір цілі для preview, не згоду на запис.

## Що потрібно перед поверненням APPLY

Окремий reviewed PR повинен реалізувати й перевірити всі пункти:

1. **Immutable typed plan.** Один типізований об'єкт містить layout, filesystem, target identity, порядок дій і digest; довільний список команд не може бути джерелом authority.
2. **Незалежна ідентичність цілі.** До планування та перед кожною destructive boundary перечитуються block-device type, major/minor, capacity, logical sector size, stable identity за наявності, partition-table digest і зв'язок кожного розділу з цільовим диском.
3. **Digest-bound consent.** Підтвердження пов'язане з конкретною ідентичністю цілі, digest усього плану та конкретною destructive дією. Згода анулюється при будь-якому дрейфі.
4. **Перевірена tool closure.** Усі абсолютні executable paths мають бути присутні у locked Guix live closure. Allowlist або текстовий шлях не доводять наявності й довіри до програми.
5. **Реальні postconditions.** GPT перечитується й порівнюється з layout; partition nodes перевіряються за major/minor та topology; filesystem — за type/UUID/label; mount — за точним source/target у mountinfo.
6. **Захищений root-agent.** Plan-файл має бути обмежений за розміром, без symlink/TOCTOU, з перевіркою ownership/permissions та чистим середовищем; root PATH і всі executable paths мають бути pinned.
7. **Відновлення.** Після збою фактичний стан перечитується; повтор destructive кроку не запускається лише на підставі журналу. Потрібні interruption/recovery semantics.
8. **Destructive acceptance лише на disposable QEMU.** Потрібні окремі scratch block devices, перевірка цілі, postconditions, підміни пристрою, interruption та незмінності сусіднього диска. Mock-тести — доповнення, не доказ APPLY safety.

До проходження цих gates підтримуваний шлях WSM завершується на read-only hardware preflight, typed data plan і preview. Не запускайте цей код на фізичному диску.
