<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

# Життєвий цикл WSM installer та системного provisioning

Це task guide для змін у `installer/`, `wsm_install/`, `systems/`, `scripts/*install*` та пов'язаних QEMU acceptance. Прочитайте [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), [INSTALLER-HANDOFF.md](../../docs/INSTALLER-HANDOFF.md) і пов'язані ADR перед роботою.

## Архітектурна межа

GNU Guix System — єдиний system/package backend першого WSM preview. Не додавайте другий package manager, власний system activation manager або паралельний механізм поколінь. Guix generations/reconfigure залишаються власником системної конфігурації та системного rollback.

Розділяйте чотири різні ролі:

1. **ISO/live orchestration** — запускає live session, preflight та UI; не вважає live root цільовою системою.
2. **System apply** — окремий backend, який змінює лише явно визначену ціль після нового підтвердження.
3. **Hardware provisioning** — ідемпотентні системні налаштування/драйвери, які можуть виконуватися на першому boot цільової системи.
4. **User provisioning** — per-user налаштування після створення облікового запису й, коли потрібно, після появи графічної сесії.

Не змішуйте машинний state, user home, generated runtime state, cache/logs та секрети. Канонічні ownership/retention правила визначає [STATELESS-CONFIGURATION.md](../../docs/STATELESS-CONFIGURATION.md); тут описано лише порядок робіт для installer/provisioning. Не створюйте дубль state manager.

## Перший підтримуваний вертикальний зріз

Поки issue #112/#169 не розширені окремим прийнятим рішенням, тримайте перший install acceptance вузьким: x86_64, UEFI, один disposable disk, ext4 root, один користувач, без encryption та dual boot. Реальний фізичний ПК не є тестовою ціллю для APPLY.



**Межа реалізації:** ця послідовність є цільовим lifecycle-контрактом, а не твердженням, що всі фази вже реалізовані. Поточні `wsm_install` partition/layout/backend модулі повертають діагностичні дані та argv; вони не виконують `APPLY`, `mkfs`, mount або `guix system init`. На звичайному non-Guix host read-only preview може містити лише allowlisted logical tool names; це не виконуваний план і не доказ наявності інструментів. На фактичній Guix System інструменти мають однозначно резолвитись тільки в `/run/current-system/profile/bin` або `sbin`; відсутність чи дубльований executable означає fail-closed. До locked Guix package-closure/build + QEMU перевірки наявність tools у live ISO має статус `not-assessed`. Див. #170, #251 та PR #574.

## Обов'язкова послідовність

Використовуйте явні фази:

`PREFLIGHT → PLAN → REVIEW → AUTHORIZE → APPLY → VERIFY → COMPLETE`

Будь-яка невідповідність переводить потік у `INCOMPLETE` або `FAILED`; не переходьте далі й не видавайте це за success.

- **PREFLIGHT** — read-only збір hardware/disk evidence. Ніяких partition writes, filesystem writes, mount changes або package installation.
- **PLAN** — чисті дані: точний target, layout, profile, locale та команди. Планувальник не запускає команди.
- **REVIEW** — UI показує користувачу реальний диск, його ідентичність, layout, операції та наслідки.
- **AUTHORIZE** — одноразове підтвердження прив'язується до target identity і digest конкретного плану.
- **APPLY** — окремий backend виконує лише дозволений типізований план.
- **VERIFY** — повторно читає фактичний стан і перевіряє кожен postcondition.
- **COMPLETE** — тільки після успішної перевірки записує завершення й пропонує reboot.

GUI не повинен генерувати shell-команди або передавати довільні рядки в shell. CLI, GUI та QEMU harness мають використовувати один backend validator і один typed plan contract.

## Контракт цільового диска та destructive consent

Перед будь-яким destructive кроком повторно перевіряйте:

- стабільну ідентичність пристрою (не лише змінний `/dev/sdX`/enumeration index);
- розмір, sector geometry та ознаки, які входять до target identity;
- поточну partition table та її digest;
- digest повного layout/plan;
- що підтвердження стосується саме цього target і цього digest.

Якщо target, його identity, layout або plan змінилися — старе підтвердження недійсне; потрібне нове. Не переносіть acknowledgement лише за шляхом пристрою й не приймайте значення з UI як доказ.

Уникайте перевірок на кшталт `path.startswith("/mnt")`: вони не відхиляють `/mnt2`, `/mnt/../etc`, symlink escape чи керівні символи. Перевіряйте канонічний шлях і дозволений mount root структурно. Усі mountpoints цільової системи мають бути під одним target root, наприклад `/mnt`, а не в live system.

## Partition та filesystem кроки — це різні операції

Не плутайте намір із фактом:

- Layout planner описує бажану таблицю розділів; він сам її не створює.
- `partprobe` і `udevadm settle` лише оновлюють видимість вже створених розділів; вони не виконують GPT partitioning.
- Перед `mkfs` треба створити partition table окремою явною операцією або read-only перевірити, що потрібні partition number/start/end/type вже існують.
- Форматування відбувається лише після повторної перевірки диска, розділу та authorization digest.
- EFI System Partition монтується всередину цілі (наприклад, `/mnt/boot/efi`), ніколи поверх live system ESP.
- Для GRUB/bootloader target має бути явно прив'язаний до цільової системи; не використовуйте ambient host boot paths.

Імена розділів відрізняються: `/dev/sda1` проти `/dev/nvme0n1p1`. Використовуйте перевірений helper, не складайте device names власноруч у кількох місцях.

## Кроки, журнал і відновлення

Кожен виконуваний крок має описувати:

- стабільний ID та тип операції;
- передумови й повторну перевірку target;
- argv як масив аргументів (не конкатенацію shell-рядка);
- очікуваний postcondition і спосіб його read-only перевірити;
- чи безпечний повтор після interruption;
- recovery/rollback або точну дію, яку треба виконати вручну.

Після кожного кроку перевіряйте фактичний стан перед переходом далі. Після перезапуску не повторюйте destructive команду тільки тому, що журнал каже `pending`: спочатку прочитайте фактичну partition/filesystem/mount/Guix generation state. Журнал може містити phase, step IDs та fingerprints, але ніколи паролі, токени, приватні ключі чи секретний вміст.

Крок, який завершився помилкою, не дозволяє виконувати залежні кроки. Не маскуйте exit code через `|| echo`, `tail -1`, grep останнього числового рядка або інші fail-open фільтри. Розрізняйте retryable, terminal failure та unknown state.

## Guix provenance та rollback

- Використовуйте точний authenticated `channels.lock.scm`, `guix time-machine` та resolved channel identity. Не покладайтеся на ambient `%default-channels`, moving branch або `--disable-authentication`.
- Build manifest пов'язує source commit, lock/profile hashes, Guix version/resolved channels, exact argv, store output та SHA-256 звичайного опублікованого артефакту.
- Build/evaluation, package closure, QEMU boot і physical hardware function — різні рівні доказу. Не підвищуйте один до іншого.
- Після системного apply зберігайте Guix generation та можливість повернутися до попередньої; user home/data не повинні бути побічно видалені під час reconfigure.
- Оновлення системи в майбутньому повинно мати один канонічний entrypoint і lock від паралельних транзакцій. Snapshot/generation boundary і post-update boot verification відбуваються до пропозиції reboot. Не копіюйте pacman guard Omarchy буквально: у WSM власник транзакції — Guix.

## First-boot hardware та user setup

Hardware provisioning, якщо воно потрібне, має бути ідемпотентним і здатним виконатися без мережі, якщо образ стверджує, що містить потрібні пакети. Якщо залежність не присутня/недоступна, крок лишається явно pending; не завантажуйте невідомий код у прихованому першому boot.

Platform-specific поведінку визначайте через наш versioned hardware evidence/provider та явні adapter-и. Не виводьте ISA/GPU/device support із `uname -m`, vendor/model string або наявності package definition. Розділяйте архітектуру ABI від конкретної hardware family.

User provisioning виконується окремо від root/system setup. Не перезаписуйте user config при кожному boot/reconfigure. Destructive resync існуючого home, якщо колись знадобиться, має бути окремою явною дією з попереднім backup/preview; він не повинен бути прихованим side effect системного update.

Для live image не вбудовуйте відомі статичні паролі. Перевіряйте root/empty-password policy, sudo/wheel membership, SDDM/console autologin і мережеву доступність разом. Empty-password console login у Guix має бути вимкнений явно, якщо цього не вимагає окремо обґрунтований installation flow.

## QEMU acceptance

Для змін live image, system profile, package, provisioning або boot path:

1. Створіть свіжий ISO з exact PR checkout; не перевіряйте нову зміну на старому ISO.
2. Boot-ніть саме WSM ISO у disposable QEMU; для першого зрізу не додавайте host disk/pass-through, host EFI variables чи фізичні пристрої.
3. Перевірте не лише base system marker: session manager, реальний Plasma/SDDM стан, preflight report, правильний користувач і відсутність привілейованого доступу.
4. Для installer slice встановлюйте лише на disposable qcow2; перевірте installed boot, hostname, user login, desktop і мережу.
5. Зберігайте raw serial/QEMU logs, screenshots та exact source/build SHA. Коли test discovery змінюється, переконайтеся в журналі, що нові тести справді виконались.

Звичайний `make check` має лишатися безпечним і не запускати тривале навантаження, Guix disk writes або фізичний hardware test. Повільні/деструктивні acceptance — окремі явні workflow/jobs.

## Джерела практик

Використані як інженерні приклади, а не залежності WSM:

- Omarchy [AGENTS.md](https://github.com/omacom/omarchy/blob/quattro/AGENTS.md), [install scripts](https://github.com/omacom/omarchy/blob/quattro/agents/skills/install-scripts.md), [migrations](https://github.com/omacom/omarchy/blob/quattro/agents/skills/migrations.md), [update process](https://github.com/omacom/omarchy/blob/quattro/docs/update-process.md), [file layout](https://github.com/omacom/omarchy/blob/quattro/docs/file-layout.md), [lifecycle dispatch](https://github.com/omacom/omarchy/blob/quattro/docs/lifecycle-dispatch.md).
- GNU Guix [System Configuration](https://guix.gnu.org/manual/en/html_node/Using-the-Configuration-System.html) та власні Guix generations.
- WSM #112, #147, #150, #169, #170 та [INSTALLER-HANDOFF.md](../../docs/INSTALLER-HANDOFF.md).

Переносьте принципи ownership, idempotency, ordered migrations, explicit destructive actions, lifecycle recovery і disposable-VM acceptance. Не переносіть Arch/pacman, Omarchy runtime, назви команд чи платформні припущення.
