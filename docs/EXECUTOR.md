# Виконання кроків інсталятора

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **лише preview; реальний APPLY вимкнено fail-closed**
- Код: [`wsm_install/executor.py`](../wsm_install/executor.py)
- Тести: `tests/test_executor.py`, `tests/test_cli_install.py`,
  `tests/test_calamares_module.py`
- Пов'язане: [#280](https://github.com/juv4uk/wsm-desktop/issues/280),
  [#286](https://github.com/juv4uk/wsm-desktop/pull/286),
  [#288](https://github.com/juv4uk/wsm-desktop/pull/288)

## Поточна межа

`execute()` має історичну назву API. Поточна реалізація **не запускає команди**:
вона формує детермінований preview argv, позначає destructive кроки та повертає
їх зі статусом `skipped`. Будь-яке значення, відмінне від буквального
`dry_run=True`, завершується `execute.apply-disabled` до виводу, runner-а,
перевірки файлової системи чи іншого зовнішнього side effect.

CLI може показати план через `wsm-install --install ...`, але параметр
`--execute` зараз навмисно відхиляється навіть за наявності однакового
`--target-disk` та `--acknowledge-disk`. Calamares jobmodule працює лише як
preview: відсутній або `None` `wsmDryRun` означає `True`; явний `False` чи
небулеве значення відхиляються до виклику executor-а. Жоден frontend не має
права самостійно створити дозвіл на запис.

`--target-size-bytes` у поточному CLI та `wsmTargetSizeBytes` у Calamares — це
передані frontend-ом значення, а не незалежний read-only probe. Їх не можна
називати перевіркою від підміни диска. Так само preview argv та абсолютний
шлях інструмента не доводять, що executable входить до locked Guix live
closure.

Preview звіряє кожен явно переданий `/dev/...` operand із зазначеним цілим
диском та його partition-node naming. Це захист від внутрішньо суперечливого
відображуваного плану, а не перевірка фактичної block-device identity,
major/minor, capacity чи partition table.

## Чому APPLY вимкнено

Перший executor prototype (#279) міг виконати довільний переданий `Step`.
Окреме підтвердження імені диска не зв'язувало argv із реальною ціллю, не було
надійної перевірки block-device identity/topology перед кожною destructive
операцією, а verifier мав неповні postconditions і використовував
`blkid` через успадкований `PATH`.

CLI шлях, доданий у #286, зробив цей executor досяжним із `--execute`.
Calamares integration #288 спочатку мала fail-open default для відсутнього
`wsmDryRun`. Поточна зміна закриває обидва шляхи у спільному executor-і та в
Calamares frontend: звичайний режим — preview, реальне виконання неможливе.

## Умови для майбутнього APPLY

Повернути реальне виконання можна лише окремою перевіреною зміною, яка має:

1. **Єдиний immutable typed plan.** Executor приймає структурований план із
   disk identity, layout, filesystem selection і allow-listed кроками; не
   довіряє довільному списку команд, створеному викликачем.
2. **Стійку ідентичність цілі.** До першого запису й перед кожною destructive
   boundary повторно читаються тип пристрою, major/minor, розмір, sector size,
   stable identity за наявності, removable/system-disk state і partition
   topology. Зміна інваріанта анулює згоду.
3. **Digest-bound consent.** Одноразове підтвердження прив'язане до повної
   target identity, digest immutable plan та конкретної destructive step;
   його перевіряють перед кожним записом.
4. **Перевірена tool closure.** Кожен executable має allow-listed absolute path
   із доказаної Guix live closure. Жодного shell, bare command або успадкованого
   `PATH`.
5. **Реальні postconditions.** GPT перечитується й порівнюється з погодженим
   layout; файлові системи перевіряються за UUID/type/label; mountinfo
   підтверджує source і target; невідомий крок завжди fail-closed.
6. **Recovery semantics.** Переривання, timeout, частковий успіх, втрата згоди
   або target drift зупиняють залежні кроки; повторний запуск спершу читає
   фактичний стан і не повторює destructive side effect навмання.
7. **Disposable QEMU acceptance.** Інтеграційний тест використовує лише
   scratch qcow2/loop-backed devices, доводить target binding, порядок GPT →
   rescan → mkfs → mount → Guix handoff, відмову при підміні пристрою,
   відсутність запису без consent та recovery після interruption.

До виконання цих умов підтримуваний шлях закінчується на read-only preflight,
typed plan і preview. Не запускайте executor на фізичному диску.

## Guided console flow

The guided console and pseudo-graphics TUI entrypoints use the same preview-only executor as CLI and
Calamares. Its planning and install callbacks return explicit exit codes:
planning failure stops before the APPLY prompt; an APPLY refusal is propagated
as a nonzero result and never prints the successful-installation message.

The TUI callback contract is also status-based: it renders its `Done` screen
only after the install callback explicitly returns zero. A refused APPLY shows
an error screen and returns a nonzero exit status.
