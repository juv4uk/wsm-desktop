# Ручний QEMU harness для WSM installer

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **локальний harness; runtime acceptance запускається вручну**
- Реалізація: `scripts/qemu_boot_smoke.py`
- Ручні guest checks: [testing/QEMU-GUEST-CI.md](testing/QEMU-GUEST-CI.md)

## Що робить harness

Project harness приймає наявний ISO-файл, перевіряє обмеження диска/RAM/CPU/часу, створює новий qcow2 у тимчасовому каталозі й запускає QEMU з TCG та вимкненою мережею. За потреби можна вимагати точний boot marker.

Serial stdout і QEMU stderr читаються паралельно в буфери обмеженого розміру. JSON-звіт містить хвіст виводу, кількість побачених байтів і прапорці обрізання. Marker шукається в усьому serial stream, навіть якщо його байти вже не входять у збережений хвіст. Після timeout процес QEMU завершується, а потоки закриваються.

Блокові пристрої передаються через структуровані QEMU `-blockdev` arguments. Host block devices не підключаються. Немає USB/GPU passthrough, shared folders або EFI variable store.

## Tool closure у завантаженій системі (#645)

Boot marker доводить, що система стартувала. Він не доводить, що інструменти, які
запускатиме інсталятор, існують у цій системі й є виконуваними — а це останній
пункт приймання #645.

`scripts/check_tool_closure.py` відповідає на це питання для каталогу, який йому
вказали. Каталог — не завантажена система. Тому тепер звіт друкує сам образ:

- shepherd-служба `wsm-tool-closure` у `systems/live-minimal.scm` запускає
  `python3 -m wsm_install.tool_closure` з того самого профілю, що містить
  інсталятор, після `WSM_LIVE_READY` і `WSM_INSTALLER_OK`;
- модуль резолвить кожен allowlisted інструмент (`wsm_install.tool_map`) за тим
  самим правилом, що й планер (`wsm_install.tools.resolve` над явними prefix-ами,
  ніколи не `PATH`), і друкує один рядок на інструмент у `/dev/console`:

```
WSM_TOOL_CLOSURE|v1|<name>|<path>|<state>
WSM_TOOL_CLOSURE_SUMMARY|v1|<ok|fail>|<usable>/<total>
```

- harness читає ці рядки з serial-виводу (`--tool-closure-marker WSM_TOOL_CLOSURE`)
  і кладе вердикт у `boot-bios.json` / `boot-uefi.json` у поле `tool_closure`, щоб
  release manifest міг його нести;
- відсутній або невиконуваний інструмент — це провал приймання: harness
  завершується з кодом 5, а не лишає boot marker замість доказу.

`--tool-closure-marker` без жодного рядка у відповіді — теж провал: тиша нічого не
доводить. `not-checked` буває лише тоді, коли перевірку не просили.

Перевірка read-only: `stat` і `access`, жодного запуску самих інструментів,
жодного mount, жодного блочного пристрою. Гість чіпає лише власний disposable
образ.

Що це доводить: у завантаженій системі кожен allowlisted шлях існує, є звичайним
файлом і є виконуваним. Чого не доводить: що це правильні інструменти, що їхній
argv зрозумілий, що вони зібрані із закріплених джерел, і що інсталятор виконав
встановлення.

## Ручний запуск

```sh
python scripts/qemu_boot_smoke.py --help
python scripts/qemu_boot_smoke.py --iso /absolute/path/to/image.iso
```

Повний прогін приймання для мінімального образу — з маркерами й перевіркою
інструментів:

```sh
python scripts/qemu_boot_smoke.py --iso /absolute/path/to/image.iso \
  --boot-marker WSM_LIVE_READY --installer-marker WSM_INSTALLER_OK \
  --tool-closure-marker WSM_TOOL_CLOSURE
```

Для повного набору disposable guest checks:

```sh
make qemu-acceptance-manual
```

Ці перевірки не запускаються автоматично в GitHub Actions. Hosted CI обмежений швидкими unit/policy tests, документацією та структурними channel checks.

## Що означає успіх

Успішний generic guest boot доводить, що конкретне ядро та init-процес запустилися під QEMU TCG. Запуск конкретного ISO доводить лише, що harness зміг стартувати цей ISO та зафіксувати потрібний marker у вибраному сценарії.

Це не доводить:

- що ISO є Guix-generated WSM image;
- що WSM installer виконав встановлення;
- що система завантажується на фізичному ПК;
- що GPU, Wi-Fi, audio, display, storage або firmware фізичного хоста сумісні.

Не використовуйте generic guest marker як hardware compatibility evidence або як заяву про готовність інсталятора.

## Ізоляція

- QEMU працює через TCG; KVM і host CPU passthrough не потрібні.
- Guest networking вимкнено.
- Writable qcow2 та тимчасові файли створюються у приватному тимчасовому каталозі й видаляються після запуску.
- Немає host disks, host block devices, USB/GPU passthrough, shared host folders або EFI variable store.
- Harness не запускає Guix/Nix deployment, firmware updater чи installer APPLY.

Документи harness-у: [QEMU-GUEST-CI.md](testing/QEMU-GUEST-CI.md) — CI-джоби й обов'язковий acceptance; [QEMU-HARNESS-INTEGRATION.md](testing/QEMU-HARNESS-INTEGRATION.md) — інтеграційний експеримент; [HWCHECK-QEMU-GUEST.md](testing/HWCHECK-QEMU-GUEST.md) — прогін колектора в гостьовій системі.
