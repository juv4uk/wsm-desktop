# Розбиття диска

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **план реалізовано, нічого не виконується**
- Код: [`wsm_install/partition.py`](../wsm_install/partition.py)
- Тести: `tests/test_partition.py` (16)

## Головне правило

`wsm_install/partition.py` **не виконує жодної команди**. Він повертає список
`sgdisk`-викликів як дані. У модулі немає коду, який відкриває блочний пристрій.

Це не обережність заради обережності. Розбиття диска — єдине місце в
інсталяторі, де помилка коштує користувачеві даних, і де «ой» не виправляється
перезапуском.

## Розкладки

**UEFI:** 512 MiB ESP (FAT32) + решта під корінь.
**BIOS:** 1 MiB `bios_grub` + решта під корінь. Мегабайт не для краси: GRUB на
GPT має кудись покласти core image.

**Swap-розділу немає навмисно.** Профіль використовує zram, а swap на SSD — це
класичний спосіб зробити десктоп повільнішим, заявляючи протилежне.

## Відмови

Планувальник відмовляє частіше, ніж погоджується. Кожна відмова має код:

| Код | Коли |
| --- | --- |
| `disk.path` | шлях не є цілим блочним пристроєм (розділ, файл-образ) |
| `disk.firmware` | firmware не `uefi` і не `bios` |
| `disk.running-system` | на цьому диску працює поточна система |
| `disk.too-small` | менше 12.5 GiB |
| `disk.acknowledgement` | на диску є дані, а підтвердження не називає саме цей диск |
| `disk.size-drift` | розмір відрізняється від очікуваного більш ніж на 2% |

Дві з них варті пояснення.

**Підтвердження мусить називати диск.** `--wipe yes` не приймається: треба
вказати `/dev/nvme0n1` рівно. Булеве «так» людина ставить на автопілоті, а назву
диска — ні.

**Розмір перевіряється окремо від імені.** `/dev/sda` на одній машині й
`/dev/nvme0n1` на іншій — це нормально. Ненормально, коли ім'я те саме, а диск
інший: саме так стирають не той носій.

## Інваріанти майбутнього APPLY: уроки сторонніх інсталяторів

Наведені випадки — вимоги до майбутнього виконавця, а не дозвіл виконувати
дискові команди зараз:

1. **Partition table не є filesystem resize.** Зміна GPT boundaries не зменшує
   файлову систему всередині. Не зменшувати NTFS без окремого підтримуваного
   offline NTFS-aware flow, перевірки та згоди; доки його немає — відмовити й
   запропонувати зменшити розділ штатним інструментом власної ОС. Джерело:
   Omarchy [#7903](https://github.com/omacom/omarchy/issues/7903).
2. **Зберігати чужі boot entries та shared ESP.** Не переписувати BootOrder,
   не очищати записи інших ОС і не видаляти їхні файли з ESP під час install/reset.
   WSM може змінювати лише ідентифіковані власні записи. Перед staging зберігати
   pre-state boot artifacts; при перериванні до root switch мати compensating
   recovery. Після операції перевіряти і файли, і boot entry. Omarchy
   [#14949](https://github.com/omacom/omarchy/pull/14949) усуває видалення
   чужих entries під час factory reset.
3. **Після кожної destructive boundary перечитувати фактичну topology.**
   Після partition-table write виконати rescan/udev settle, заново прочитати
   geometry, start/end, number, type та filesystem identity. Шлях
   `/dev/sda2` або `/dev/nvme0n1p2` не є доказом, що це той самий погоджений
   розділ.
4. **Перевіряти boot artifact, а не тільки exit code.** Kernel/UKI, initrd,
   boot entry та `root=` мають вказувати на ту саму generation і target root.
   Перевірка root identity та cmdline потрібна до package/kernel transaction,
   а після build треба перевірити embedded cmdline нового artifact. Omarchy
   [#6951](https://github.com/omacom/omarchy/pull/6951) виправляв випадок, коли
   оновлений UKI втрачав `root=` і машина потрапляла в emergency shell.
5. **Interrupted encryption operation не відновлювати лише за journal.**
   Повторна зміна LUKS key має довести, який саме slot був створений цією
   операцією, і не видаляти невідомий/recovery key. Omarchy
   [#14874](https://github.com/omacom/omarchy/pull/14874) показує цей клас
   помилки. Для першого WSM install slice encryption залишається поза scope,
   доки немає окремого protocol та interruption tests.
6. **CSM і multi-disk не є прихованим success.** Перший install vertical slice
   залишається x86_64, UEFI та одним disposable disk. Omarchy
   [#20178](https://github.com/omacom/omarchy/issues/20178) досі відкрита:
   legacy/CSM install на другий диск може завершитися, але firmware продовжує
   завантажувати іншу ОС. Майбутня підтримка цього режиму потребуватиме окремого
   boot-handoff verdict; коли порядок firmware неможливо перевірити, повертати
   `MANUAL_BOOT_ORDER_REQUIRED`, а не `COMPLETE`.

Ці вимоги доповнюють target-bound consent та фази
`PREFLIGHT → PLAN → REVIEW → AUTHORIZE → APPLY → VERIFY → COMPLETE` у
[INSTALLER-HANDOFF.md](INSTALLER-HANDOFF.md). Поточний partition planner лише
повертає argv як дані; він не виконує `sgdisk`, `mkfs`, mount або bootloader
зміни.
## Чого ще немає

- **Виконання.** Модуль не викликає `sgdisk`. Хтось має це зробити свідомо, з
  перевіркою після кожного кроку.
- **Файлових систем.** Немає `mkfs.fat` для ESP і `mkfs.ext4`/btrfs для кореня.
- **Монтування й передачі в `guix system init`.**
- **Перевірки, що диск справді той.** Розмір — груба перевірка; серійний номер
  надійніший, але він має бути в звіті про залізо.
- **Відкату.** Якщо розбиття почалося й обірвалося — план відновлення не описаний.
