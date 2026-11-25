# Послідовність встановлення

<!-- SPDX-License-Identifier: LicenseRef-Volnist -->

- Статус: **не-виконуваний план; executor відсутній**
- Код: [`wsm_install/install_steps.py`](../wsm_install/install_steps.py)
- Джерело розкладки: [`wsm_install/partition.py`](../wsm_install/partition.py)
- Тести: `tests/test_install_steps.py`

## Що це

Модуль складає послідовність від запланованої GPT-розкладки до
підготовленого mount tree й фіксованого Guix handoff. Він повертає тільки
масиви аргументів та позначки destructive; жодної команди не запускає, не
відкриває block device й не монтує файлову систему.

`Layout` із partition planner описує **намір**, а не вже записану таблицю
розділів; він зберігає розмір диска на момент планування та точний шлях,
який користувач підтвердив. Підтвердження потрібне навіть для диска, який
інвентаризація позначила порожнім: `sgdisk --zap-all` усе одно замінює його
partition table. Тому install sequence включає `sgdisk`-операції до
`partprobe` і `udevadm settle`. `partprobe` перечитує таблицю — не створює її.

## Повний план UEFI для прикладу NVMe

Усі рядки нижче — лише preview. Кожна операція `sgdisk` і `mkfs` має
позначку **DESTRUCTIVE** у структурованому результаті. Шляхи інструментів —
абсолютні всередині `/run/current-system/profile`, а не `/usr` і не успадкований `PATH`.

```sh
/run/current-system/profile/sbin/sgdisk --zap-all /dev/nvme0n1
/run/current-system/profile/sbin/sgdisk --new=1:1MiB:513MiB --typecode=1:ef00 --change-name=1:wsm-esp /dev/nvme0n1
/run/current-system/profile/sbin/sgdisk --new=2:513MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/nvme0n1
/run/current-system/profile/sbin/partprobe /dev/nvme0n1
/run/current-system/profile/bin/udevadm settle
/run/current-system/profile/sbin/mkfs.ext4 -F /dev/nvme0n1p2
/run/current-system/profile/sbin/mkfs.fat -F 32 /dev/nvme0n1p1
/run/current-system/profile/bin/mount /dev/nvme0n1p2 /mnt
/run/current-system/profile/bin/mkdir -p /mnt/boot/efi
/run/current-system/profile/bin/mount /dev/nvme0n1p1 /mnt/boot/efi
/run/current-system/profile/bin/guix time-machine -C /run/wsm/channels.lock.scm -- system init /run/wsm/system.scm /mnt
```

## Запобіжники

**Підтвердження диска переноситься разом із розкладкою.** Partition planner
вимагає підтвердження, яке точно називає цільовий вузол, навіть якщо
інвентаризація позначила диск як порожній. `Layout` зберігає підтвердження
та спостережений розмір; якщо будь-яке з них втрачено, `plan_steps()` і
`backend_command()` відмовляють. Виконавець перед APPLY все одно мусить
повторно перевірити major/minor, розмір і topology.

**Повна GPT-розкладка перед форматуванням.** `sgdisk --zap-all` і
створення partition entries передують `partprobe`, `udevadm settle` та
`mkfs`. Усі ці GPT-записи й форматування явно позначені destructive.

**Абсолютні шляхи утиліт.** Усі привілейовані disk tools беруться з
`TRUSTED_TOOLS` і запускаються через абсолютні шляхи, а не шукаються у
поточному `PATH`. Команди повертаються як argv-масиви; shell не є частиною
планувальника.

**Mount target фіксований.** Приймається лише точний `/mnt`; `/tmp`,
`/mnt2`, `/mnt/../root`, альтернативні абсолютні шляхи та newline
відхиляються, а не нормалізуються.

**Жодного довільного Scheme-файлу.** Backend argv будується спільним
`backend_guix.build_argv()` і має форму
`/run/current-system/profile/bin/guix time-machine -C /run/wsm/channels.lock.scm -- system init
/run/wsm/system.scm /mnt`. Це pinned handoff preview; channel lock і
згенерований конфіг мають бути staged та перевірені до будь-якого майбутнього
виконання.

**Правильне ім'я розділу й ESP.** `/dev/sda` + 1 = `/dev/sda1`, але
`/dev/nvme0n1` + 1 = `/dev/nvme0n1p1`. UEFI ESP монтується у
`/mnt/boot/efi`, не в live-систему. BIOS layout має `bios_grub` і не
створює ESP/FAT filesystem.

## Чому зараз лише ext4

Поточний Guix renderer генерує root filesystem як ext4. Тому planner також
дозволяє лише ext4: Btrfs і XFS відхиляються, доки вибір filesystem не стане
частиною typed install plan/digest і не буде переданий у той самий Guix
renderer. Форматувати Btrfs, а в декларації встановленої системи записати
ext4 — неприпустима невідповідність.

## Чого ще немає

- **Executor-а.** Немає коду, що запускає `sgdisk`, `mkfs`, `mount` або
  `guix time-machine ... system init`; цей модуль лише формує дані.
- **Повторної ідентифікації block device перед APPLY.** Майбутній executor
  має звірити поточні major/minor, розмір і partition topology з
  підтвердженим планом безпосередньо перед першою мутацією.
- **Staging inputs.** Копіювання authenticated `channels.lock.scm` і
  generated `operating-system` у `/run/wsm/` ще не реалізовано.
- **Перевірки після кожної фази та відновлення.** Потрібні журнал фаз і
  задокументована поведінка після переривання.
- **UUID у фінальній конфігурації.** Імена `/dev/...` використовуються
  лише для плану; майбутній `fstab`/boot config має спиратися на перевірені
  filesystem UUID.
- **Tool closure proof.** Абсолютні шляхи `/run/current-system/profile/...` є запланованими, але присутність кожної утиліти в live ISO ще не доведена; це окремий locked Guix package/ISO acceptance gate у #170.
- **Guix end-to-end proof.** Пін-форма argv ще не є доказом, що staged lock
  автентифікується в live-середовищі або що система встановлюється і
  завантажується з disposable QEMU disk.

До появи цих перевірок послідовність — лише матеріал для огляду, не дозвіл
на запис у фізичний диск і не готовий інсталятор.
